/** @odoo-module **/

import { Component, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";

// Building an Intl formatter is far more expensive than using one: create them once
// instead of calling toLocale*String(locale, options) for every item and axis label.
const TIME_FORMAT = new Intl.DateTimeFormat('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
const DAY_TITLE_FORMAT = new Intl.DateTimeFormat('en-US', { weekday: 'short', day: '2-digit', month: 'long' });
const MONTH_YEAR_FORMAT = new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' });
const SHORT_MONTH_FORMAT = new Intl.DateTimeFormat('en-US', { month: 'short' });
const DATETIME_FORMAT = new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
});

export class GanttRenderer extends Component {
    setup() {
        this.ganttRef = useRef("gantt");
        this.timeline = null;
        this.itemsById = new Map();  // record items by vis id, for click/tooltip lookups

        // What the timeline currently shows, so re-renders only redo what changed
        this._renderedEl = null;
        this._renderedData = null;
        this._renderedScale = null;

        this.state = useState({
            isLoading: false,
        });

        onMounted(() => {
            this.renderGantt();
        });

        onPatched(() => {
            this.refreshGantt();
        });

        onWillUnmount(() => {
            this._destroyTimeline();
        });
    }

    renderGantt() {
        this._destroyTimeline();

        const el = this.ganttRef.el;
        if (!el) {
            // No data: the template shows the "no content" helper instead
            return;
        }

        if (!window.vis || !window.vis.Timeline) {
            console.error("[web_gantt] vis-timeline library not loaded");
            return;
        }

        const { model, scale } = this.props;
        const data = model.data;
        if (!data || !data.groups || Object.keys(data.groups).length === 0) {
            return;
        }

        const { groups, items } = this._buildTimelineData(data);

        try {
            this.timeline = new window.vis.Timeline(
                el,
                new window.vis.DataSet(items),
                new window.vis.DataSet(groups),
                this._getTimelineOptions(scale)
            );

            this.timeline.on('click', (properties) => {
                const item = properties.item != null && this.itemsById.get(properties.item);
                if (item) {
                    this.onTaskClick(item.task);
                }
            });
        } catch (error) {
            console.error("[web_gantt] Error initializing timeline:", error);
            this._destroyTimeline();
            return;
        }

        this._renderedEl = el;
        this._renderedData = data;
        this._renderedScale = scale;
    }

    /**
     * Sync the timeline with the current props, touching only what changed:
     * items are rebuilt when the model loaded new data, a scale change only
     * updates the axis and the visible window.
     */
    refreshGantt() {
        if (!this.timeline || this.ganttRef.el !== this._renderedEl) {
            // First data after an empty result, or the container was re-created
            this.renderGantt();
            return;
        }

        const { model, scale } = this.props;
        const data = model.data;
        const dataChanged = data !== this._renderedData;
        const scaleChanged = scale !== this._renderedScale;
        if (!dataChanged && !scaleChanged) {
            return;
        }

        try {
            if (dataChanged) {
                const { groups, items } = this._buildTimelineData(data);
                // Clear the items before swapping groups: vis matches every existing
                // item against each added group, which is O(groups x items).
                this.timeline.setItems(null);
                this.timeline.setGroups(new window.vis.DataSet(groups));
                this.timeline.setItems(new window.vis.DataSet(items));
            }
            if (scaleChanged) {
                this.timeline.setOptions(this._getScaleOptions(scale));
            }
            this._setVisibleWindow(scale);
        } catch (error) {
            console.error("[web_gantt] Error refreshing timeline:", error);
        }

        this._renderedData = data;
        this._renderedScale = scale;
    }

    _destroyTimeline() {
        if (this.timeline) {
            this.timeline.destroy();
            this.timeline = null;
        }
        this._renderedEl = null;
        this._renderedData = null;
        this._renderedScale = null;
    }

    /**
     * Build vis groups and items for the whole dataset. Everything goes into a
     * single DataSet: vis re-sorts all items on every add/remove event, so items
     * must never be added one by one.
     */
    _buildTimelineData(data) {
        const { archInfo } = this.props;
        const groups = [];
        const items = [];
        this.itemsById = new Map();

        for (const [groupKey, groupData] of Object.entries(data.groups)) {
            groups.push({
                id: groupKey,
                content: this._getGroupContent(groupData),
                order: groups.length,  // Maintain order
            });

            for (const task of groupData.tasks) {
                const item = {
                    id: task.id,
                    group: groupKey,
                    start: task.start,
                    end: task.end,
                    content: this._getItemContent(task, archInfo),
                    className: task.custom_class || '',
                    task,
                };
                items.push(item);
                this.itemsById.set(item.id, item);
            }
        }

        for (const extraItem of this._getExtraItems(data)) {
            items.push(extraItem);
        }

        return { groups, items };
    }

    /**
     * Hook for additional (e.g. background) items that belong in the timeline
     * alongside the records.
     */
    _getExtraItems(data) {
        return [];
    }

    _getGroupContent(groupData) {
        if (!groupData.attendanceState) {
            return groupData.label;
        }
        const statusClass = groupData.attendanceState === 'checked_in' ? 'checked-in' : 'checked-out';
        const indicatorTitle = groupData.attendanceState === 'checked_in' ? 'Currently checked in' : 'Currently checked out';
        return `<span class="attendance-status-indicator ${statusClass}" title="${indicatorTitle}"></span><span>${groupData.label}</span>`;
    }

    _getTimelineOptions(scale) {
        const { archInfo } = this.props;
        return {
            // Initial window. It must be an option: vis fits the view to all items once the
            // first draw is done, which overrides a setWindow() call made right after creation
            // (and then renders every record instead of only the visible period).
            ...this._getScaleWindow(scale),

            // Layout
            orientation: 'top',
            stack: false,  // Don't stack items vertically - keep all on one line per employee
            groupOrder: 'order',
            groupHeightMode: 'fixed',  // Fixed height for consistency

            // Allow HTML in group and item labels
            xss: {
                disabled: false,
                filterOptions: {
                    whiteList: {
                        span: ['style', 'title', 'class'],
                    },
                },
            },

            // Scale
            ...this._getScaleOptions(scale),

            // Interaction
            editable: {
                add: archInfo.canCreate,
                updateTime: archInfo.canEdit && !archInfo.disableDragDrop,
                updateGroup: false,
                remove: archInfo.canDelete,
                overrideItems: false,
            },

            // Selection
            selectable: true,
            multiselect: false,

            // Styling - improved spacing
            margin: {
                item: {
                    horizontal: 2,     // Horizontal spacing between items
                    vertical: 8,       // Vertical spacing for better visibility
                },
                axis: 5,
            },

            // Item alignment and height
            align: 'center',
            verticalScroll: true,
            horizontalScroll: true,
            zoomable: true,
            zoomKey: 'ctrlKey',        // Ctrl+scroll to zoom

            // Tooltip
            tooltip: {
                followMouse: true,
                overflowMethod: 'cap',
                // Built on hover instead of up front for every record
                template: (itemData) => {
                    const item = itemData && this.itemsById.get(itemData.id);
                    return item ? this._getItemTitle(item.task, this.props.archInfo) : '';
                },
            },
        };
    }

    _setVisibleWindow(scale) {
        if (!this.timeline) return;

        const range = this._getScaleWindow(scale);
        if (range) {
            this.timeline.setWindow(range.start, range.end);
        }
    }

    _getScaleWindow(scale) {
        const now = new Date();
        let start, end;

        switch (scale) {
            case 'day':
                // Show today with hourly detail
                start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
                end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);
                break;
            case 'week':
                // Show current week
                const dayOfWeek = now.getDay();
                const diff = now.getDate() - dayOfWeek + (dayOfWeek === 0 ? -6 : 1); // Adjust for Monday start
                start = new Date(now.getFullYear(), now.getMonth(), diff);
                end = new Date(start);
                end.setDate(start.getDate() + 6);
                break;
            case 'month':
                // Show current month
                start = new Date(now.getFullYear(), now.getMonth(), 1);
                end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
                break;
            case 'year':
                // Show current year
                start = new Date(now.getFullYear(), 0, 1);
                end = new Date(now.getFullYear(), 11, 31);
                break;
            default:
                return null;
        }

        return { start, end };
    }

    // Day separators and weekend shading come from the time axis grid (see gantt_view.scss)
    _getScaleOptions(scale) {
        // Helper to convert whatever vis-timeline passes to a Date object
        const toDate = (d) => {
            if (d instanceof Date) return d;
            if (typeof d === 'number') return new Date(d);
            if (typeof d === 'string') return new Date(d);
            // Handle moment-like objects
            if (d && typeof d.toDate === 'function') return d.toDate();
            if (d && typeof d.valueOf === 'function') return new Date(d.valueOf());
            return new Date(d);
        };

        const scaleOptions = {
            day: {
                timeAxis: { scale: 'hour', step: 1 },
                format: {
                    minorLabels: (d) => TIME_FORMAT.format(toDate(d)),
                    majorLabels: (d) => DAY_TITLE_FORMAT.format(toDate(d)),
                },
            },
            week: {
                timeAxis: { scale: 'day', step: 1 },
                format: {
                    minorLabels: (d) => {
                        const date = toDate(d);
                        return date.getDate().toString().padStart(2, '0');
                    },
                    majorLabels: (d) => {
                        const date = toDate(d);
                        const weekNum = this._getWeekNumber(date);
                        return `Week ${weekNum} ${date.getFullYear()}`;
                    },
                },
            },
            month: {
                timeAxis: { scale: 'day', step: 1 },
                format: {
                    minorLabels: (d) => {
                        const date = toDate(d);
                        return date.getDate().toString().padStart(2, '0');
                    },
                    majorLabels: (d) => MONTH_YEAR_FORMAT.format(toDate(d)),
                },
            },
            year: {
                timeAxis: { scale: 'month', step: 1 },
                format: {
                    minorLabels: (d) => SHORT_MONTH_FORMAT.format(toDate(d)),
                    majorLabels: (d) => {
                        const date = toDate(d);
                        return date.getFullYear().toString();
                    },
                },
            },
        };

        return scaleOptions[scale] || scaleOptions.week;
    }

    _getWeekNumber(date) {
        const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
        const dayNum = d.getUTCDay() || 7;
        d.setUTCDate(d.getUTCDate() + 4 - dayNum);
        const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
        return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    }

    _formatHoursMinutes(value) {
        if (!value) return '0h';
        let hours = Math.floor(Math.abs(value));
        let minutes = Math.round((Math.abs(value) - hours) * 60);
        if (minutes === 60) {
            minutes = 0;
            hours += 1;
        }
        const sign = value < 0 ? '-' : '';
        if (minutes === 0) {
            return `${sign}${hours}h`;
        }
        return `${sign}${hours}h ${minutes}min`;
    }

    _getItemContent(task, archInfo) {
        // Extract worked hours for display
        const record = task.record;
        const workedHours = record.worked_hours;

        if (workedHours) {
            return this._formatHoursMinutes(workedHours);
        }

        return '';
    }

    _getItemTitle(task, archInfo) {
        const record = task.record;
        const parts = [];

        // Add employee name
        if (record.employee_id && Array.isArray(record.employee_id)) {
            parts.push(`Employee: ${record.employee_id[1]}`);
        }

        // Add worked hours
        if (record.worked_hours) {
            parts.push(`Worked: ${this._formatHoursMinutes(record.worked_hours)}`);
        }

        // Add overtime
        if (record.overtime_hours) {
            parts.push(`Overtime: ${this._formatHoursMinutes(record.overtime_hours)}`);
        }

        // Add date range
        const startStr = this._formatDateTime(task.start);
        const endStr = this._formatDateTime(task.end);
        parts.push(`${startStr} - ${endStr}`);

        return parts.join('\n');
    }

    _formatDateTime(date) {
        if (!date) return '';
        const d = date instanceof Date ? date : new Date(date);
        return DATETIME_FORMAT.format(d);
    }

    onTaskClick(task) {
        // Always open form view on click - the form view will handle permissions
        // Opening a record for viewing should always be allowed
        const action = {
            type: "ir.actions.act_window",
            res_model: this.props.archInfo.modelName,
            res_id: task.recordId,
            views: [[false, "form"]],
            target: "current",
        };
        this.env.services.action.doAction(action);
    }

    get hasData() {
        const { model } = this.props;
        return model.data && model.data.groups && Object.keys(model.data.groups).length > 0;
    }
}

GanttRenderer.template = "web_gantt.GanttRenderer";
GanttRenderer.props = [
    "model",
    "archInfo",
    "scale",
    "onTaskUpdate?",
    "onTaskDelete?",
    "onTaskCreate?",
    "onTaskClick?",
    "onScaleChange?",
];
