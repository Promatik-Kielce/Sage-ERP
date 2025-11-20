/** @odoo-module **/

import { visitXML } from "@web/core/utils/xml";

export class GanttArchParser {
    parse(arch, models, modelName) {
        console.log("[web_gantt] ArchParser.parse called with:", { arch, models, modelName });

        let root;
        if (typeof arch === "string") {
            const xmlDoc = new DOMParser().parseFromString(arch, "text/xml");
            root = xmlDoc.querySelector("gantt");
        } else if (arch instanceof Element) {
            root = arch.tagName === "gantt" ? arch : arch.querySelector("gantt");
        } else if (arch instanceof Document) {
            root = arch.querySelector("gantt");
        } else {
            console.error("[web_gantt] Unexpected arch type:", typeof arch, arch);
            throw new Error("Invalid gantt view architecture: unexpected arch type");
        }

        if (!root) {
            console.error("[web_gantt] No gantt root element found in arch:", arch);
            throw new Error("Invalid gantt view architecture: no gantt element found");
        }

        console.log("[web_gantt] Found gantt root element:", root);

        const defaultGroupBy = root.getAttribute("default_group_by");
        console.log("[web_gantt] ArchParser - default_group_by attribute:", defaultGroupBy);

        const result = {
            // Required attributes
            dateStartField: root.getAttribute("date_start"),
            dateStopField: root.getAttribute("date_stop"),

            // Optional attributes
            dateDelayField: root.getAttribute("date_delay"),
            defaultScale: root.getAttribute("default_scale") || "month",
            colorField: root.getAttribute("color"),
            progressField: root.getAttribute("progress"),
            defaultGroupBy: defaultGroupBy,
            precision: root.getAttribute("precision"),
            scales: root.getAttribute("scales") || "day,week,month,year",
            totalRow: root.getAttribute("total_row") === "true",
            plan: root.getAttribute("plan") !== "false",
            disableDragDrop: root.getAttribute("disable_drag_drop") === "true",

            // CRUD permissions
            canCreate: root.getAttribute("create") !== "false",
            canEdit: root.getAttribute("edit") !== "false",
            canDelete: root.getAttribute("delete") !== "false",
            canCellCreate: root.getAttribute("cell_create") !== "false",

            // Field information
            fields: {},
            fieldNames: [],

            modelName,
        };

        // Parse fields
        visitXML(root, (node) => {
            if (node.tagName === "field") {
                const fieldName = node.getAttribute("name");
                const fieldInfo = {
                    name: fieldName,
                    string: node.getAttribute("string"),
                    invisible: node.getAttribute("invisible") === "1",
                };
                result.fields[fieldName] = fieldInfo;
                result.fieldNames.push(fieldName);
            }
        });

        // Add required fields to fieldNames if not already there
        const requiredFields = [
            result.dateStartField,
            result.dateStopField,
            result.dateDelayField,
            result.colorField,
            result.progressField,
            result.defaultGroupBy,
        ].filter(Boolean);

        for (const field of requiredFields) {
            if (!result.fieldNames.includes(field)) {
                result.fieldNames.push(field);
                result.fields[field] = { name: field };
            }
        }

        return result;
    }
}
