/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { GanttModel } from "@web_gantt/gantt_model";
import { GanttRenderer } from "@web_gantt/gantt_renderer";
import { onWillUnmount } from "@odoo/owl";

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

        if (!records || records.length === 0) {
            this.data.leaves = [];
            return;
        }

        const employeeIds = [
            ...new Set(
                records
                    .filter(r => Array.isArray(r.employee_id))
                    .map(r => r.employee_id[0])
            )
        ];

        if (employeeIds.length === 0) {
            this.data.leaves = [];
            return;
        }

        const checkIns = records
            .filter(r => r.check_in)
            .map(r => new Date(r.check_in).getTime());
        const checkOuts = records
            .filter(r => r.check_out)
            .map(r => new Date(r.check_out).getTime());

        if (checkIns.length === 0) {
            this.data.leaves = [];
            return;
        }

        const rangeStart = new Date(Math.min(...checkIns));
        const rangeEnd = checkOuts.length > 0 ? new Date(Math.max(...checkOuts)) : new Date();

        const toOdooDatetime = (d) => {
            const pad = (n) => String(n).padStart(2, '0');
            return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
                   `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
        };

        try {
            const leaves = await this.orm.searchRead(
                'hr.leave',
                [
                    ['employee_id', 'in', employeeIds],
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
        } catch (error) {
            console.error("[attendance_gantt_patch] Error fetching leaves:", error);
            this.data.leaves = [];
        }
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
        this._leaveItemIds = [];
        this._leaveTooltipEl = null;

        onWillUnmount(() => {
            if (this._leaveTooltipEl) {
                if (this.ganttRef.el) {
                    this.ganttRef.el.removeEventListener('mousemove', this._leaveMouseMove);
                    this.ganttRef.el.removeEventListener('mouseleave', this._leaveMouseLeave);
                }
                this._leaveTooltipEl.remove();
                this._leaveTooltipEl = null;
            }
        });
    },

    renderGantt() {
        super.renderGantt(...arguments);

        if (this.props.archInfo.modelName !== 'hr.attendance') {
            return;
        }

        this._addLeaveItems();
        this._setupLeaveTooltip();
    },

    refreshGantt() {
        super.refreshGantt(...arguments);

        if (this.props.archInfo.modelName !== 'hr.attendance') {
            return;
        }

        this._addLeaveItems();
    },

    /**
     * Add leave periods as background items.
     * Background items fill the full row height and are never repositioned
     * by vis-timeline's layout engine.
     */
    _addLeaveItems() {
        if (!this.timeline) return;

        const leaves = this.props.model.data.leaves;
        if (!leaves || leaves.length === 0) return;

        this._removeLeaveItems();

        const groups = this.props.model.data.groups;
        const items = this.timeline.itemsData;
        if (!items) return;

        this._leaveItemIds = [];

        for (const leave of leaves) {
            if (!leave.employee_id || !leave.date_from || !leave.date_to) continue;

            const employeeId = leave.employee_id[0];
            const groupKey = `employee_${employeeId}`;

            if (!groups || !groups[groupKey]) continue;

            const bgId = `leave-bg-${leave.id}-${employeeId}`;
            this._leaveItemIds.push(bgId);

            const colorClass = `gantt-color-${leave._color || 0}`;

            try {
                items.add({
                    id: bgId,
                    group: groupKey,
                    start: new Date(leave.date_from),
                    end: new Date(leave.date_to),
                    type: 'background',
                    className: `vis-leave-background ${colorClass}`,
                    content: '',
                });
            } catch (e) {
                // Item already exists — skip
            }
        }
    },

    _removeLeaveItems() {
        if (!this.timeline || !this._leaveItemIds || this._leaveItemIds.length === 0) {
            return;
        }

        try {
            const items = this.timeline.itemsData;
            if (items) {
                for (const id of this._leaveItemIds) {
                    try { items.remove(id); } catch (e) { /* ignore */ }
                }
            }
        } catch (e) { /* ignore */ }

        this._leaveItemIds = [];
    },

    /**
     * Create a custom tooltip that shows leave info on mousemove.
     * Uses timeline.getEventProperties() to detect the employee group
     * and time under the cursor, then matches against leave records.
     */
    _setupLeaveTooltip() {
        // Only create once
        if (this._leaveTooltipEl) return;

        const el = this.ganttRef.el;
        if (!el || !this.timeline) return;

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

        const formatDate = (d) => new Date(d).toLocaleDateString('pl-PL', {
            day: '2-digit', month: '2-digit', year: 'numeric',
        });

        this._leaveMouseMove = (event) => {
            const leaves = this.props.model.data && this.props.model.data.leaves;
            if (!leaves || leaves.length === 0) {
                tip.style.display = 'none';
                return;
            }

            let props;
            try {
                props = this.timeline.getEventProperties(event);
            } catch (e) {
                tip.style.display = 'none';
                return;
            }

            // If hovering an attendance bar, let its own title tooltip show
            if (props.item && this.items && this.items.some(i => i.id === props.item)) {
                tip.style.display = 'none';
                return;
            }

            if (!props.group || !props.time) {
                tip.style.display = 'none';
                return;
            }

            const groupKey = String(props.group);
            if (!groupKey.startsWith('employee_')) {
                tip.style.display = 'none';
                return;
            }

            const employeeId = parseInt(groupKey.replace('employee_', ''), 10);
            const mouseTime = props.time instanceof Date ? props.time : new Date(props.time);

            const leave = leaves.find(l =>
                Array.isArray(l.employee_id) &&
                l.employee_id[0] === employeeId &&
                mouseTime >= new Date(l.date_from) &&
                mouseTime <= new Date(l.date_to)
            );

            if (leave) {
                const leaveType = Array.isArray(leave.holiday_status_id)
                    ? leave.holiday_status_id[1] : 'Urlop';
                const duration = leave.duration_display || `${leave.number_of_days} d`;
                tip.textContent =
                    `${leaveType}\n` +
                    `${leave.employee_id[1]}\n` +
                    `${formatDate(leave.date_from)} \u2013 ${formatDate(leave.date_to)}\n` +
                    `${duration}`;
                tip.style.display = 'block';
                tip.style.left = (event.clientX + 16) + 'px';
                tip.style.top = (event.clientY + 16) + 'px';
            } else {
                tip.style.display = 'none';
            }
        };

        this._leaveMouseLeave = () => {
            tip.style.display = 'none';
        };

        el.addEventListener('mousemove', this._leaveMouseMove);
        el.addEventListener('mouseleave', this._leaveMouseLeave);
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
        const leaves = this.props.model.data.leaves;
        if (!leaves || leaves.length === 0 || !Array.isArray(record.employee_id)) {
            return baseTitle;
        }

        const empId = record.employee_id[0];
        const checkIn = record.check_in ? new Date(record.check_in) : null;
        if (!checkIn) return baseTitle;

        const matchingLeaves = leaves.filter(leave => {
            if (!Array.isArray(leave.employee_id) || leave.employee_id[0] !== empId) {
                return false;
            }
            return checkIn >= new Date(leave.date_from) && checkIn <= new Date(leave.date_to);
        });

        if (matchingLeaves.length === 0) {
            return baseTitle;
        }

        const formatDate = (d) => new Date(d).toLocaleDateString('pl-PL', {
            day: '2-digit', month: '2-digit', year: 'numeric',
        });

        const separator = '\u2500'.repeat(22);

        let leaveLines = '';
        for (const leave of matchingLeaves) {
            const leaveType = Array.isArray(leave.holiday_status_id)
                ? leave.holiday_status_id[1] : 'Urlop';
            const duration = leave.duration_display || `${leave.number_of_days} d`;
            leaveLines +=
                `${leaveType}\n` +
                `${formatDate(leave.date_from)} \u2013 ${formatDate(leave.date_to)}\n` +
                `${duration}\n`;
        }

        return `${baseTitle}\n${separator}\n${leaveLines.trimEnd()}`;
    },
});
