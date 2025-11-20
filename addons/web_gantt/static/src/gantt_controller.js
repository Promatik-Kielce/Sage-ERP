/** @odoo-module **/

import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { Layout } from "@web/search/layout";

export class GanttController extends Component {
    setup() {
        // Instantiate model directly
        this.model = new this.props.Model(
            this.env.services.orm,
            {
                modelName: this.props.resModel,
                archInfo: this.props.archInfo,
            },
            null
        );

        this.state = useState({
            scale: this.props.archInfo.defaultScale,
        });

        onWillStart(async () => {
            await this.loadData();
        });

        onWillUpdateProps(async (nextProps) => {
            if (nextProps.domain !== this.props.domain ||
                nextProps.context !== this.props.context ||
                nextProps.groupBy !== this.props.groupBy) {
                await this.loadData(nextProps);
            }
        });
    }

    async loadData(props = this.props) {
        // Use search groupBy if available, otherwise use default from view definition
        let groupBy = props.groupBy || [];
        console.log("[web_gantt] Controller.loadData - props.groupBy:", props.groupBy);
        console.log("[web_gantt] Controller.loadData - props.archInfo.defaultGroupBy:", props.archInfo.defaultGroupBy);

        // If we have a default_group_by from the view, prioritize it
        if (props.archInfo.defaultGroupBy) {
            // Look for the default group field in the groupBy array
            const defaultField = props.archInfo.defaultGroupBy;
            const hasDefaultField = groupBy.some(g => g.split(':')[0] === defaultField);

            if (hasDefaultField) {
                // Filter to only use the default group field
                groupBy = groupBy.filter(g => g.split(':')[0] === defaultField);
                console.log("[web_gantt] Controller.loadData - Filtered to default groupBy:", groupBy);
            } else if (groupBy.length === 0) {
                // No groupBy from search, use default
                groupBy = [defaultField];
                console.log("[web_gantt] Controller.loadData - Using default groupBy:", groupBy);
            }
        }

        const searchParams = {
            context: props.context || {},
            domain: props.domain || [],
            groupBy: groupBy,
            orderBy: props.orderBy || "",
        };

        console.log("[web_gantt] Controller.loadData - Final searchParams.groupBy:", searchParams.groupBy);
        await this.model.load(searchParams);
    }

    get rendererProps() {
        return {
            model: this.model,
            archInfo: this.props.archInfo,
            scale: this.state.scale,
            onTaskUpdate: this.onTaskUpdate.bind(this),
            onTaskDelete: this.onTaskDelete.bind(this),
            onTaskCreate: this.onTaskCreate.bind(this),
            onScaleChange: this.onScaleChange.bind(this),
        };
    }

    async onTaskUpdate(taskId, start, end) {
        if (!this.props.archInfo.canEdit) {
            return;
        }
        await this.model.updateTask(taskId, start, end);
    }

    async onTaskDelete(taskId) {
        if (!this.props.archInfo.canDelete) {
            return;
        }
        await this.model.deleteTask(taskId);
    }

    async onTaskCreate() {
        if (!this.props.archInfo.canCreate) {
            return;
        }
        // Open form view for creating new record
        const action = {
            type: "ir.actions.act_window",
            res_model: this.props.resModel,
            views: [[false, "form"]],
            target: "new",
            context: this.props.context,
        };
        await this.env.services.action.doAction(action);
    }

    onScaleChange(scale) {
        this.state.scale = scale;
    }

    async openRecord(recordId) {
        const action = {
            type: "ir.actions.act_window",
            res_model: this.props.resModel,
            res_id: recordId,
            views: [[false, "form"]],
            target: "current",
            context: this.props.context,
        };
        await this.env.services.action.doAction(action);
    }
}

GanttController.template = "web_gantt.GanttController";
GanttController.components = { Layout };
GanttController.props = {
    // Required props
    resModel: String,
    fields: Object,
    archInfo: Object,
    Model: Function,
    Renderer: Function,
    buttonTemplate: String,

    // Optional view props
    domain: { type: Array, optional: true },
    context: { type: Object, optional: true },
    groupBy: { type: Array, optional: true },
    orderBy: { optional: true }, // Can be string or array
    display: { type: Object, optional: true },

    // Generic action props
    info: { type: Object, optional: true },
    arch: { optional: true },
    relatedModels: { type: Object, optional: true },
    useSampleModel: { type: Boolean, optional: true },
    className: { type: String, optional: true },
    globalState: { type: Object, optional: true },
    selectRecord: { type: Function, optional: true },
    createRecord: { type: Function, optional: true },
    limit: { type: Number, optional: true },
    resId: { optional: true },
    resIds: { type: Array, optional: true },
    updateActionState: { type: Function, optional: true },
    noBreadcrumbs: { type: Boolean, optional: true },
    searchMenuTypes: { type: Array, optional: true },

    // Any other props
    "*": true,
};
