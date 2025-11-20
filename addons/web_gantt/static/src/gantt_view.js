/** @odoo-module **/

import { registry } from "@web/core/registry";
import { GanttArchParser } from "./gantt_arch_parser";
import { GanttController } from "./gantt_controller";
import { GanttModel } from "./gantt_model";
import { GanttRenderer } from "./gantt_renderer";

console.log("[web_gantt] Gantt view module loading...");

export const ganttView = {
    type: "gantt",
    display_name: "Gantt",
    icon: "fa fa-tasks",
    multiRecord: true,
    searchMenuTypes: ["filter", "groupBy", "favorite"],

    Controller: GanttController,
    Renderer: GanttRenderer,
    Model: GanttModel,
    ArchParser: GanttArchParser,

    buttonTemplate: "web_gantt.GanttController.Buttons",

    props: (genericProps, view) => {
        console.log("[web_gantt] Creating props for gantt view", genericProps);
        const { ArchParser, Model, Renderer, buttonTemplate } = view;
        const { arch, relatedModels, resModel, fields } = genericProps;

        const archInfo = new ArchParser().parse(arch, relatedModels, resModel);
        console.log("[web_gantt] Parsed archInfo:", archInfo);

        return {
            ...genericProps,
            Model,
            Renderer,
            buttonTemplate,
            archInfo,
            fields: fields || {},
        };
    },
};

console.log("[web_gantt] Registering gantt view in registry...", ganttView);
registry.category("views").add("gantt", ganttView);
console.log("[web_gantt] Gantt view registered successfully!");
