/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { GanttModel } from "@web_gantt/gantt_model";
import { GanttRenderer } from "@web_gantt/gantt_renderer";
import { onWillUnmount } from "@odoo/owl";

const LEAVE_DATE_FORMAT = new Intl.DateTimeFormat('pl-PL', {
    day: '2-digit', month: '2-digit', year: 'numeric',
});

const formatDate = (d) => LEAVE_DATE_FORMAT.format(new Date(d));

function formatLeave(leave) {
    const leaveType = Array.isArray(leave.holiday_status_id)
        ? leave.holiday_status_id[1] : 'Urlop';
    const duration = leave.duration_display || `${leave.number_of_days} d`;
    return { leaveType, duration };
}

// ─────────────────────────────────────────────────────────────────────────────
// GanttModel patch — fetch approved hr.leave records alongside attendance data
// ─────────────────────────────────────────────────────────────────────────────
patch(GanttModel.prototype, {
    async load(searchParams) {
        await super.load(...arguments);

        if (this.config.modelName !== 'hr.attendance') {
            return this.data;
        }

        await this._fetchLeaves();
        return this.data;
    },

    async _fetchLeaves() {
        const records = this.data.records;
        this.data.leaves = [];
        this.data.leavesByEmployee = new Map();

        if (!records || records.length === 0) {
            return;
        }

        // Single pass (no Math.min(...spread): it overflows the stack on large sets)
        const employeeIds = new Set();
        let rangeStartTs = Infinity;
        let rangeEndTs = -Infinity;
        for (const record of records) {
            if (Array.isArray(record.employee_id)) {
                employeeIds.add(record.employee_id[0]);
            }
            if (record.check_in) {
                rangeStartTs = Math.min(rangeStartTs, new Date(record.check_in).getTime());
            }
            if (record.check_out) {
                rangeEndTs = Math.max(rangeEndTs, new Date(record.check_out).getTime());
            }
        }

        if (employeeIds.size === 0 || rangeStartTs === Infinity) {
            return;
        }

        const rangeStart = new Date(rangeStartTs);
        const rangeEnd = rangeEndTs > -Infinity ? new Date(rangeEndTs) : new Date();

        const toOdooDatetime = (d) => {
            const pad = (n) => String(n).padStart(2, '0');
            return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
                   `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
        };

        try {
            const leaves = await this.orm.searchRead(
                'hr.leave',
                [
                    ['employee_id', 'in', [...employeeIds]],
                    ['state', '=', 'validate'],
                    ['date_from', '<=', toOdooDatetime(rangeEnd)],
                    ['date_to', '>=', toOdooDatetime(rangeStart)],
                ],
                ['employee_id', 'date_from', 'date_to', 'holiday_status_id', 'number_of_days', 'duration_display'],
                {}
            );

            // Fetch leave type colors
            const leaveTypeIds = [...new Set(
                leaves.filter(l => Array.isArray(l.holiday_status_id))
                      .map(l => l.holiday_status_id[0])
            )];

            if (leaveTypeIds.length > 0) {
                const leaveTypes = await this.orm.searchRead(
                    'hr.leave.type',
                    [['id', 'in', leaveTypeIds]],
                    ['id', 'color'],
                    {}
                );
                const colorMap = {};
                for (const lt of leaveTypes) {
                    colorMap[lt.id] = lt.color || 0;
                }
                for (const leave of leaves) {
                    if (Array.isArray(leave.holiday_status_id)) {
                        leave._color = colorMap[leave.holiday_status_id[0]] || 0;
                    }
                }
            }

            this.data.leaves = leaves;
            this.data.leavesByEmployee = this._indexLeavesByEmployee(leaves);
        } catch (error) {
            console.error("[attendance_gantt_patch] Error fetching leaves:", error);
            this.data.leaves = [];
            this.data.leavesByEmployee = new Map();
        }
    },

    /**
     * Group leaves per employee with their bounds parsed once, so tooltips and
     * hover lookups only scan one employee's leaves.
     */
    _indexLeavesByEmployee(leaves) {
        const leavesByEmployee = new Map();
        for (const leave of leaves) {
            if (!Array.isArray(leave.employee_id) || !leave.date_from || !leave.date_to) {
                continue;
            }
            const employeeId = leave.employee_id[0];
            if (!leavesByEmployee.has(employeeId)) {
                leavesByEmployee.set(employeeId, []);
            }
            leavesByEmployee.get(employeeId).push({
                start: new Date(leave.date_from).getTime(),
                end: new Date(leave.date_to).getTime(),
                leave,
            });
        }
        return leavesByEmployee;
    },
});

// ─────────────────────────────────────────────────────────────────────────────
// GanttRenderer patch — render hr.leave records as background items with
// custom mousemove tooltip.
//
// Background items are immune to vis-timeline's selection/repositioning —
// they never jump or shift. Tooltip is shown via a mousemove listener on the
// timeline container using timeline.getEventProperties() to detect which
// employee row and time the cursor is over.
// ─────────────────────────────────────────────────────────────────────────────
patch(GanttRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this._leaveTooltipEl = null;
        this._leaveTooltipTarget = null;
        this._leaveMouseEvent = null;
        this._leaveFrame = null;

        onWillUnmount(() => {
            this._teardownLeaveTooltip();
        });
    },

    renderGantt() {
        super.renderGantt(...arguments);

        if (this.timeline && this.props.archInfo.modelName === 'hr.attendance') {
            this._setupLeaveTooltip();
        }
    },

    /**
     * Leave periods as background items. They are part of the initial DataSet
     * (adding them one by one makes vis re-sort every item each time).
     * Background items fill the full row height and are never repositioned
     * by vis-timeline's layout engine.
     */
    _getExtraItems(data) {
        const extraItems = super._getExtraItems(...arguments);

        if (this.props.archInfo.modelName !== 'hr.attendance' || !data.leavesByEmployee) {
            return extraItems;
        }

        for (const [employeeId, entries] of data.leavesByEmployee) {
            const groupKey = `employee_${employeeId}`;
            if (!data.groups[groupKey]) {
                continue;
            }
            for (const { start, end, leave } of entries) {
                extraItems.push({
                    id: `leave-bg-${leave.id}-${employeeId}`,
                    group: groupKey,
                    start: new Date(start),
                    end: new Date(end),
                    type: 'background',
                    className: `vis-leave-background gantt-color-${leave._color || 0}`,
                    content: '',
                });
            }
        }

        return extraItems;
    },

    /**
     * Create a custom tooltip that shows leave info on mousemove.
     * Uses timeline.getEventProperties() to detect the employee group
     * and time under the cursor, then matches against leave records.
     */
    _setupLeaveTooltip() {
        const el = this.ganttRef.el;
        if (!el || el === this._leaveTooltipTarget) {
            return;
        }

        if (!this._leaveTooltipEl) {
            // Create tooltip div on document.body to avoid overflow/z-index issues
            const tip = document.createElement('div');
            tip.style.cssText = [
                'display: none',
                'position: fixed',
                'pointer-events: none',
                'z-index: 9999',
                'padding: 8px 12px',
                'background: #ffffff',
                'border: 1px solid #dee2e6',
                'border-radius: 4px',
                'box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15)',
                'color: #212529',
                'font-size: 12px',
                'line-height: 1.5',
                'max-width: 300px',
                'white-space: pre-line',
                'font-family: sans-serif',
            ].join('; ') + ';';
            document.body.appendChild(tip);
            this._leaveTooltipEl = tip;

            // mousemove fires far more often than the screen refreshes:
            // only handle the latest event once per frame.
            this._leaveMouseMove = (event) => {
                this._leaveMouseEvent = event;
                if (!this._leaveFrame) {
                    this._leaveFrame = requestAnimationFrame(() => {
                        this._leaveFrame = null;
                        this._updateLeaveTooltip(this._leaveMouseEvent);
                    });
                }
            };

            this._leaveMouseLeave = () => {
                this._cancelLeaveFrame();
                tip.style.display = 'none';
            };
        }

        // The container is re-created when the view goes empty and back
        if (this._leaveTooltipTarget) {
            this._leaveTooltipTarget.removeEventListener('mousemove', this._leaveMouseMove);
            this._leaveTooltipTarget.removeEventListener('mouseleave', this._leaveMouseLeave);
        }
        el.addEventListener('mousemove', this._leaveMouseMove);
        el.addEventListener('mouseleave', this._leaveMouseLeave);
        this._leaveTooltipTarget = el;
    },

    _updateLeaveTooltip(event) {
        const tip = this._leaveTooltipEl;
        const hide = () => {
            tip.style.display = 'none';
        };

        const data = this.props.model.data;
        const leavesByEmployee = data && data.leavesByEmployee;
        if (!this.timeline || !leavesByEmployee || leavesByEmployee.size === 0) {
            hide();
            return;
        }

        let props;
        try {
            props = this.timeline.getEventProperties(event);
        } catch (e) {
            hide();
            return;
        }

        // If hovering an attendance bar, let its own title tooltip show
        if (props.item && this.itemsById.has(props.item)) {
            hide();
            return;
        }

        if (!props.group || !props.time) {
            hide();
            return;
        }

        const groupKey = String(props.group);
        if (!groupKey.startsWith('employee_')) {
            hide();
            return;
        }

        const employeeId = parseInt(groupKey.replace('employee_', ''), 10);
        const mouseTime = (props.time instanceof Date ? props.time : new Date(props.time)).getTime();

        const entry = (leavesByEmployee.get(employeeId) || []).find(
            ({ start, end }) => mouseTime >= start && mouseTime <= end
        );

        if (entry) {
            const { leave } = entry;
            const { leaveType, duration } = formatLeave(leave);
            tip.textContent =
                `${leaveType}\n` +
                `${leave.employee_id[1]}\n` +
                `${formatDate(leave.date_from)} – ${formatDate(leave.date_to)}\n` +
                `${duration}`;
            tip.style.display = 'block';
            tip.style.left = (event.clientX + 16) + 'px';
            tip.style.top = (event.clientY + 16) + 'px';
        } else {
            hide();
        }
    },

    _cancelLeaveFrame() {
        if (this._leaveFrame) {
            cancelAnimationFrame(this._leaveFrame);
            this._leaveFrame = null;
        }
    },

    _teardownLeaveTooltip() {
        this._cancelLeaveFrame();
        if (this._leaveTooltipTarget) {
            this._leaveTooltipTarget.removeEventListener('mousemove', this._leaveMouseMove);
            this._leaveTooltipTarget.removeEventListener('mouseleave', this._leaveMouseLeave);
            this._leaveTooltipTarget = null;
        }
        if (this._leaveTooltipEl) {
            this._leaveTooltipEl.remove();
            this._leaveTooltipEl = null;
        }
    },

    /**
     * Append leave info to the attendance bar tooltip when the check-in falls
     * within an approved leave — separated by a visual divider line.
     */
    _getItemTitle(task, archInfo) {
        const baseTitle = super._getItemTitle(...arguments);

        if (archInfo.modelName !== 'hr.attendance') {
            return baseTitle;
        }

        const record = task.record;
        const leavesByEmployee = this.props.model.data.leavesByEmployee;
        if (!leavesByEmployee || leavesByEmployee.size === 0 || !Array.isArray(record.employee_id)) {
            return baseTitle;
        }

        if (!record.check_in) {
            return baseTitle;
        }
        const checkIn = new Date(record.check_in).getTime();

        const matchingLeaves = (leavesByEmployee.get(record.employee_id[0]) || []).filter(
            ({ start, end }) => checkIn >= start && checkIn <= end
        );

        if (matchingLeaves.length === 0) {
            return baseTitle;
        }

        const separator = '─'.repeat(22);

        let leaveLines = '';
        for (const { leave } of matchingLeaves) {
            const { leaveType, duration } = formatLeave(leave);
            leaveLines +=
                `${leaveType}\n` +
                `${formatDate(leave.date_from)} – ${formatDate(leave.date_to)}\n` +
                `${duration}\n`;
        }

        return `${baseTitle}\n${separator}\n${leaveLines.trimEnd()}`;
    },
});
