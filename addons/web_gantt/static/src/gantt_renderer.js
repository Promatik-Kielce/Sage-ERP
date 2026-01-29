/** @odoo-module **/

import { Component, onMounted, onPatched, onWillUnmount, useRef, useState } from "@odoo/owl";

export class GanttRenderer extends Component {
    setup() {
        this.ganttRef = useRef("gantt");
        this.timeline = null;
        this.items = [];  // Store items as instance variable for event handler access

        this.state = useState({
            isLoading: false,
        });

        onMounted(() => {
            this.renderGantt();
        });

        onPatched(() => {
            if (this.timeline) {
                this.refreshGantt();
            }
        });

        onWillUnmount(() => {
            if (this.timeline) {
                this.timeline.destroy();
                this.timeline = null;
            }
        });
    }

    renderGantt() {
        if (!this.ganttRef.el) {
            console.error("[web_gantt] Gantt container element not available");
            return;
        }

        if (!window.vis || !window.vis.Timeline) {
            console.error("[web_gantt] vis-timeline library not loaded");
            return;
        }

        const { model, archInfo, scale } = this.props;
        const data = model.data;

        console.log("[web_gantt] Rendering timeline with data:", data);

        if (!data || !data.groups || Object.keys(data.groups).length === 0) {
            console.log("[web_gantt] No groups (employees) to render");
            return;
        }

        // Prepare groups (employees) and items (attendance records)
        const groups = [];
        this.items = [];  // Reset items array

        Object.entries(data.groups).forEach(([groupKey, groupData]) => {
            // Create label with attendance state indicator
            console.log("[web_gantt] Rendering group:", groupKey, "Label:", groupData.label, "AttendanceState:", groupData.attendanceState);
            let labelHTML = groupData.label;
            if (groupData.attendanceState) {
                console.log("[web_gantt] Adding status indicator for", groupKey, "State:", groupData.attendanceState);
                const statusClass = groupData.attendanceState === 'checked_in' ? 'checked-in' : 'checked-out';
                const indicatorTitle = groupData.attendanceState === 'checked_in' ? 'Currently checked in' : 'Currently checked out';
                labelHTML = `<span class="attendance-status-indicator ${statusClass}" title="${indicatorTitle}"></span><span>${groupData.label}</span>`;
            }

            // Add employee as a group
            groups.push({
                id: groupKey,
                content: labelHTML,
                order: groups.length,  // Maintain order
            });

            // Add attendance records as items
            groupData.tasks.forEach(task => {
                const item = {
                    id: task.id,
                    group: groupKey,
                    start: new Date(task.start),  // Convert to Date object
                    end: new Date(task.end),      // Convert to Date object
                    content: this._getItemContent(task, archInfo),
                    title: this._getItemTitle(task, archInfo),
                    className: task.custom_class || '',
                    task: task,  // Store task data for click handling
                };
                this.items.push(item);
            });
        });

        console.log("[web_gantt] Groups:", groups);
        console.log("[web_gantt] Items:", this.items);

        // Timeline options
        const options = {
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
            },
        };

        // Create timeline
        try {
            this.timeline = new window.vis.Timeline(
                this.ganttRef.el,
                new window.vis.DataSet(this.items),
                new window.vis.DataSet(groups),
                options
            );

            // Bind events - use 'click' event for more reliable click detection
            this.timeline.on('click', (properties) => {
                console.log("[web_gantt] Click event:", properties);
                if (properties.item) {
                    const itemId = properties.item;
                    const item = this.items.find(i => i.id === itemId);
                    console.log("[web_gantt] Found item:", item);
                    if (item && item.task) {
                        this.onTaskClick(item.task);
                    }
                }
            });

            this.timeline.on('rangechange', (properties) => {
                // User dragged an item
                if (properties.byUser) {
                    this.onTaskDateChange(properties);
                }
            });

            // Update day separators when view range changes
            this.timeline.on('rangechanged', () => {
                this._addDaySeparators(this.props.scale);
            });

            // Set initial visible window based on scale
            this._setVisibleWindow(scale);

            // Add day separator lines
            this._addDaySeparators(scale);

        } catch (error) {
            console.error("[web_gantt] Error initializing timeline:", error);
        }
    }

    _addDaySeparators(scale) {
        if (!this.timeline) return;

        // Remove existing day separators
        this._removeDaySeparators();

        // Only add separators for week/month scales where days need to be distinguished
        if (scale !== 'week' && scale !== 'month') return;

        const window = this.timeline.getWindow();
        const start = new Date(window.start);
        const end = new Date(window.end);

        // Start from beginning of the first day
        const current = new Date(start.getFullYear(), start.getMonth(), start.getDate());
        current.setDate(current.getDate() + 1); // Start from next day boundary

        this._daySeparatorIds = [];
        this._weekendBackgroundIds = [];

        while (current < end) {
            const dayOfWeek = current.getDay();
            const id = `day-sep-${current.getTime()}`;
            try {
                this.timeline.addCustomTime(current, id);
                this._daySeparatorIds.push(id);
            } catch (e) {
                // Custom time already exists, skip
            }

            // Check if this day is a weekend (Saturday=6 or Sunday=0)
            // Add background item for weekend days
            if (dayOfWeek === 0 || dayOfWeek === 6) {
                const weekendStart = new Date(current);
                weekendStart.setHours(0, 0, 0, 0);
                const weekendEnd = new Date(current);
                weekendEnd.setDate(weekendEnd.getDate() + 1); // End at next day midnight
                weekendEnd.setHours(0, 0, 0, 0);

                const bgId = `weekend-bg-${current.getTime()}`;
                this._weekendBackgroundIds.push({
                    id: bgId,
                    start: weekendStart,
                    end: weekendEnd,
                    type: 'background',
                    className: 'vis-weekend-background',
                });
            }

            current.setDate(current.getDate() + 1);
        }

        // Add weekend background items to the timeline
        this._addWeekendBackgrounds();
    }

    _addWeekendBackgrounds() {
        if (!this.timeline || !this._weekendBackgroundIds || this._weekendBackgroundIds.length === 0) return;

        try {
            const items = this.timeline.itemsData;
            if (items) {
                this._weekendBackgroundIds.forEach(bg => {
                    try {
                        items.add(bg);
                    } catch (e) {
                        // Item might already exist
                    }
                });
            }
        } catch (e) {
            console.log("[web_gantt] Could not add weekend backgrounds:", e);
        }
    }

    _removeDaySeparators() {
        if (!this.timeline) return;

        // Remove custom time markers
        if (this._daySeparatorIds) {
            this._daySeparatorIds.forEach(id => {
                try {
                    this.timeline.removeCustomTime(id);
                } catch (e) {
                    // Ignore if already removed
                }
            });
            this._daySeparatorIds = [];
        }

        // Remove weekend background items
        if (this._weekendBackgroundIds && this._weekendBackgroundIds.length > 0) {
            try {
                const items = this.timeline.itemsData;
                if (items) {
                    this._weekendBackgroundIds.forEach(bg => {
                        try {
                            items.remove(bg.id);
                        } catch (e) {
                            // Ignore if already removed
                        }
                    });
                }
            } catch (e) {
                // Ignore errors
            }
            this._weekendBackgroundIds = [];
        }
    }

    _setVisibleWindow(scale) {
        if (!this.timeline) return;

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
                return;
        }

        this.timeline.setWindow(start, end);
    }

    refreshGantt() {
        if (!this.timeline) {
            this.renderGantt();
            return;
        }

        const { model, archInfo, scale } = this.props;
        const data = model.data;

        if (!data || !data.groups) {
            return;
        }

        // Update groups and items
        const groups = [];
        this.items = [];  // Reset items array

        Object.entries(data.groups).forEach(([groupKey, groupData]) => {
            // Create label with attendance state indicator
            console.log("[web_gantt] Refreshing group:", groupKey, "Label:", groupData.label, "AttendanceState:", groupData.attendanceState);
            let labelHTML = groupData.label;
            if (groupData.attendanceState) {
                console.log("[web_gantt] Adding status indicator (refresh) for", groupKey, "State:", groupData.attendanceState);
                const statusClass = groupData.attendanceState === 'checked_in' ? 'checked-in' : 'checked-out';
                const indicatorTitle = groupData.attendanceState === 'checked_in' ? 'Currently checked in' : 'Currently checked out';
                labelHTML = `<span class="attendance-status-indicator ${statusClass}" title="${indicatorTitle}"></span><span>${groupData.label}</span>`;
            }

            groups.push({
                id: groupKey,
                content: labelHTML,
                order: groups.length,
            });

            groupData.tasks.forEach(task => {
                this.items.push({
                    id: task.id,
                    group: groupKey,
                    start: new Date(task.start),  // Convert to Date object
                    end: new Date(task.end),      // Convert to Date object
                    content: this._getItemContent(task, archInfo),
                    title: this._getItemTitle(task, archInfo),
                    className: task.custom_class || '',
                    task: task,
                });
            });
        });

        try {
            this.timeline.setGroups(new window.vis.DataSet(groups));
            this.timeline.setItems(new window.vis.DataSet(this.items));
            this.timeline.setOptions(this._getScaleOptions(scale));
            // Update visible window when scale changes
            this._setVisibleWindow(scale);
            // Re-add day separators for new scale/window
            this._addDaySeparators(scale);
        } catch (error) {
            console.error("[web_gantt] Error refreshing timeline:", error);
        }
    }

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
                    minorLabels: (d) => {
                        const date = toDate(d);
                        return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
                    },
                    majorLabels: (d) => {
                        const date = toDate(d);
                        return date.toLocaleDateString('en-US', { weekday: 'short', day: '2-digit', month: 'long' });
                    },
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
                    majorLabels: (d) => {
                        const date = toDate(d);
                        return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
                    },
                },
            },
            year: {
                timeAxis: { scale: 'month', step: 1 },
                format: {
                    minorLabels: (d) => {
                        const date = toDate(d);
                        return date.toLocaleDateString('en-US', { month: 'short' });
                    },
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
        return d.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    }

    onTaskClick(task) {
        console.log("[web_gantt] Task clicked:", task);
        console.log("[web_gantt] canEdit:", this.props.archInfo.canEdit);
        console.log("[web_gantt] modelName:", this.props.archInfo.modelName);
        console.log("[web_gantt] recordId:", task.recordId);

        // Always open form view on click - the form view will handle permissions
        // Opening a record for viewing should always be allowed
        const action = {
            type: "ir.actions.act_window",
            res_model: this.props.archInfo.modelName,
            res_id: task.recordId,
            views: [[false, "form"]],
            target: "current",
        };
        console.log("[web_gantt] Opening action:", action);
        this.env.services.action.doAction(action);
    }

    async onTaskDateChange(properties) {
        // Handle date changes if editing is enabled
        console.log("[web_gantt] Date change:", properties);

        if (this.props.onTaskUpdate && !this.props.archInfo.disableDragDrop) {
            // Update would be handled here
            // For now, refresh to revert changes since we're read-only
            this.refreshGantt();
        }
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
