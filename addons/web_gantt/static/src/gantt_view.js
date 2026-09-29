/** @odoo-module **/

import { registry } from "@web/core/registry";
import { GanttArchParser } from "./gantt_arch_parser";
import { GanttController } from "./gantt_controller";
import { GanttModel } from "./gantt_model";
import { GanttRenderer } from "./gantt_renderer";

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
        const { ArchParser, Model, Renderer, buttonTemplate } = view;
        const { arch, relatedModels, resModel, fields } = genericProps;

        const archInfo = new ArchParser().parse(arch, relatedModels, resModel);

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

registry.category("views").add("gantt", ganttView);
