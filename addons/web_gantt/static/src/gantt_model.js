/** @odoo-module **/

import { KeepLast } from "@web/core/utils/concurrency";
import { deserializeDate, deserializeDateTime } from "@web/core/l10n/dates";
import { Domain } from "@web/core/domain";

export class GanttModel {
    constructor(orm, config, data) {
        this.orm = orm;
        this.config = config;
        this.data = data || {};
        this.keepLast = new KeepLast();
    }

    /**
     * Load gantt data from the server
     */
    async load(searchParams) {
        const {
            context,
            domain,
            groupBy,
            orderBy,
        } = searchParams;

        const { modelName, archInfo } = this.config;

        // Extract field names from groupBy (remove granularity like :month, :week)
        const groupByFields = (groupBy || []).map(g => g.split(':')[0]);

        // Build fields to fetch
        const fields = [
            ...archInfo.fieldNames,
            archInfo.dateStartField,
            archInfo.dateStopField,
            archInfo.colorField,
            archInfo.progressField,
            // Ensure groupBy field is included (without granularity)
            ...groupByFields,
        ].filter(Boolean);

        // Remove duplicates
        const uniqueFields = [...new Set(fields)];

        console.log("[web_gantt] Loading data with fields:", uniqueFields);
        console.log("[web_gantt] GroupBy:", groupBy);
        console.log("[web_gantt] GroupBy fields extracted:", groupByFields);

        // Fetch records
        const result = await this.keepLast.add(
            this.orm.searchRead(
                modelName,
                domain,
                uniqueFields,
                {
                    context,
                    order: orderBy,
                }
            )
        );

        // Transform records to gantt format
        const tasks = this._transformRecords(result, archInfo);

        // Group tasks if needed
        const groups = this._groupTasks(tasks, groupBy, archInfo);

        // Fetch employee attendance states if grouping by employee
        if (groupBy.length > 0 && groupBy[0].split(':')[0] === 'employee_id') {
            await this._fetchEmployeeStates(groups);
        }

        this.data = {
            tasks,
            groups,
            groupBy: groupBy.length > 0 ? groupBy[0] : null,
            scale: archInfo.defaultScale,
            records: result,
        };

        return this.data;
    }

    /**
     * Transform Odoo records to Frappe Gantt format
     */
    _transformRecords(records, archInfo) {
        return records.map(record => {
            const startDate = this._parseDate(record[archInfo.dateStartField]);
            let endDate;

            if (archInfo.dateStopField && record[archInfo.dateStopField]) {
                endDate = this._parseDate(record[archInfo.dateStopField]);
            } else if (archInfo.dateDelayField && record[archInfo.dateDelayField]) {
                // Calculate end date from start + delay (delay in days)
                endDate = new Date(startDate);
                endDate.setDate(endDate.getDate() + record[archInfo.dateDelayField]);
            } else {
                // Default to same day
                endDate = new Date(startDate);
            }

            // Get color class based on color field value
            let customClass = "";
            if (archInfo.colorField && record[archInfo.colorField] !== undefined) {
                const colorValue = record[archInfo.colorField];
                customClass = `gantt-color-${colorValue}`;
            }

            // Get progress (0-100)
            let progress = 0;
            if (archInfo.progressField && record[archInfo.progressField] !== undefined) {
                progress = Math.min(100, Math.max(0, record[archInfo.progressField]));
            }

            // Get task name with employee and hours
            let name = `#${record.id}`;
            let employeeName = null;
            let workedHours = null;

            for (const fieldName of archInfo.fieldNames) {
                const value = record[fieldName];
                if (fieldName === 'employee_id' && Array.isArray(value) && value.length === 2) {
                    employeeName = value[1];
                } else if (fieldName === 'worked_hours' && value) {
                    workedHours = value;
                } else if (!employeeName && value && typeof value === 'string') {
                    name = value;
                } else if (!employeeName && Array.isArray(value) && value.length === 2) {
                    name = value[1];
                }
            }

            // Build display name with employee and hours
            if (employeeName) {
                name = workedHours ? `${employeeName} (${workedHours}h)` : employeeName;
            }

            return {
                id: `record_${record.id}`,
                recordId: record.id,
                name,
                start: startDate,
                end: endDate,
                progress,
                custom_class: customClass,
                record,
            };
        });
    }

    /**
     * Parse date/datetime field to JavaScript Date
     */
    _parseDate(value) {
        if (!value) {
            return new Date();
        }

        if (typeof value === 'string') {
            // Try datetime first, then date
            try {
                return deserializeDateTime(value).toJSDate();
            } catch (e) {
                try {
                    return deserializeDate(value).toJSDate();
                } catch (e2) {
                    // Fallback to native parsing
                    return new Date(value);
                }
            }
        }

        return value instanceof Date ? value : new Date(value);
    }

    /**
     * Group tasks by a field
     */
    _groupTasks(tasks, groupBy, archInfo) {
        console.log("[web_gantt] Grouping tasks. GroupBy:", groupBy, "Tasks count:", tasks.length);

        if (!groupBy || groupBy.length === 0) {
            console.log("[web_gantt] No groupBy, returning all tasks in default group");
            return { "all": { label: "All Records", tasks } };
        }

        // Extract base field name (remove granularity like :month, :week)
        const groupField = groupBy[0].split(':')[0];
        console.log("[web_gantt] Group field (base):", groupField);
        const groups = {};

        for (const task of tasks) {
            let groupKey = "undefined";
            let groupLabel = "Undefined";

            const record = task.record;
            console.log("[web_gantt] Processing task:", task.recordId, "GroupField value:", record[groupField]);

            if (record[groupField] !== undefined && record[groupField] !== false) {
                const value = record[groupField];
                if (Array.isArray(value) && value.length === 2) {
                    // Many2one: [id, name]
                    groupKey = `employee_${value[0]}`;  // Prefix to ensure string key
                    groupLabel = value[1];
                    console.log("[web_gantt] Many2one field. Key:", groupKey, "Label:", groupLabel);
                } else {
                    groupKey = `group_${value}`;
                    groupLabel = value.toString();
                    console.log("[web_gantt] Other field. Key:", groupKey, "Label:", groupLabel);
                }
            } else {
                console.log("[web_gantt] Field is undefined/false for task:", task.recordId);
            }

            if (!groups[groupKey]) {
                groups[groupKey] = {
                    label: groupLabel,
                    tasks: [],
                };
                console.log("[web_gantt] Created new group:", groupKey, "Label:", groupLabel);
            }
            groups[groupKey].tasks.push(task);
        }

        console.log("[web_gantt] Final groups:", Object.keys(groups).map(k => ({key: k, label: groups[k].label, count: groups[k].tasks.length})));
        return groups;
    }

    /**
     * Update a task's dates
     */
    async updateTask(taskId, start, end) {
        const task = this.data.tasks.find(t => t.id === taskId);
        if (!task) {
            return;
        }

        const { archInfo, modelName } = this.config;
        const updateData = {};

        updateData[archInfo.dateStartField] = this._serializeDate(start);

        if (archInfo.dateStopField) {
            updateData[archInfo.dateStopField] = this._serializeDate(end);
        } else if (archInfo.dateDelayField) {
            // Calculate delay in days
            const delay = Math.round((end - start) / (1000 * 60 * 60 * 24));
            updateData[archInfo.dateDelayField] = delay;
        }

        await this.orm.write(modelName, [task.recordId], updateData);

        // Update local data
        task.start = start;
        task.end = end;
        task.record[archInfo.dateStartField] = this._serializeDate(start);
        if (archInfo.dateStopField) {
            task.record[archInfo.dateStopField] = this._serializeDate(end);
        }
    }

    /**
     * Serialize JavaScript Date to Odoo format
     */
    _serializeDate(date) {
        if (!date) return false;

        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');

        // Return datetime format (Odoo uses UTC)
        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    }

    /**
     * Delete a task
     */
    async deleteTask(taskId) {
        const task = this.data.tasks.find(t => t.id === taskId);
        if (!task) {
            return;
        }

        await this.orm.unlink(this.config.modelName, [task.recordId]);

        // Remove from local data
        this.data.tasks = this.data.tasks.filter(t => t.id !== taskId);
    }

    /**
     * Fetch employee attendance states for groups
     */
    async _fetchEmployeeStates(groups) {
        // Extract employee IDs from group keys
        const employeeIds = [];
        for (const groupKey in groups) {
            if (groupKey.startsWith('employee_')) {
                const employeeId = parseInt(groupKey.replace('employee_', ''));
                if (!isNaN(employeeId)) {
                    employeeIds.push(employeeId);
                }
            }
        }

        if (employeeIds.length === 0) {
            return;
        }

        // Fetch employee attendance states
        try {
            const employees = await this.orm.searchRead(
                'hr.employee',
                [['id', 'in', employeeIds]],
                ['id', 'attendance_state'],
                {}
            );

            // Map states to groups
            for (const employee of employees) {
                const groupKey = `employee_${employee.id}`;
                if (groups[groupKey]) {
                    groups[groupKey].attendanceState = employee.attendance_state;
                    console.log("[web_gantt] Set attendanceState for", groupKey, "to", employee.attendance_state);
                } else {
                    console.warn("[web_gantt] Group not found for", groupKey);
                }
            }

            console.log("[web_gantt] Fetched employee states:", employees);
            console.log("[web_gantt] Groups after setting states:", Object.keys(groups).map(k => ({key: k, label: groups[k].label, state: groups[k].attendanceState})));
        } catch (error) {
            console.error("[web_gantt] Error fetching employee states:", error);
        }
    }
}
