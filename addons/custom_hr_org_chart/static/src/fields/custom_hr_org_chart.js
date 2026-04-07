/** @odoo-module **/

import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

async function callJsonRpc(url, params = {}) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params,
            id: Date.now(),
        }),
    });

    if (!response.ok) {
        throw new Error(`RPC HTTP error ${response.status}`);
    }

    const payload = await response.json();

    if (payload.error) {
        const message =
            payload.error?.data?.message ||
            payload.error?.message ||
            "Unknown RPC error";
        throw new Error(message);
    }

    return payload.result;
}

export class CustomHrOrgChart extends Component {
    static template = "custom_hr_org_chart.hr_org_chart";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.action = useService("action");
        this.state = useState({
            managers: [],
            children: [],
            self: {},
            managers_more: false,
        });

        onWillStart(async () => {
            await this.fetchOrgData(this.props);
        });

        onWillUpdateProps(async (nextProps) => {
            if (nextProps.record.resId !== this.props.record.resId) {
                await this.fetchOrgData(nextProps);
            }
        });
    }

    get employeeId() {
        return this.props.record.resId;
    }

    async fetchOrgData(props) {
        if (!props.record.resId) {
            this.state.managers = [];
            this.state.children = [];
            this.state.self = {};
            this.state.managers_more = false;
            return;
        }

        const result = await callJsonRpc("/hr/get_multi_org_chart", {
            employee_id: props.record.resId,
            context: props.record.context || {},
        });

        this.state.managers = result.managers || [];
        this.state.children = result.children || [];
        this.state.self = result.self || {};
        this.state.managers_more = !!result.managers_more;
    }

    async _onEmployeeRedirect(employeeId) {
        const redirectModel = await callJsonRpc("/hr/get_redirect_model", {});
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: redirectModel,
            res_id: employeeId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async _onEmployeeMoreManager(employeeId) {
        await this._onEmployeeRedirect(employeeId);
    }

    async _onEmployeeSubRedirect(ev) {
        const employeeId = parseInt(ev.currentTarget.dataset.employeeId, 10);
        const subordinatesType = ev.currentTarget.dataset.type || "total";

        const redirectModel = await callJsonRpc("/hr/get_redirect_model", {});
        const subordinateIds = await callJsonRpc("/hr/get_subordinates", {
            employee_id: employeeId,
            subordinates_type: subordinatesType,
            context: this.props.record.context || {},
        });

        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Subordinates",
            res_model: redirectModel,
            views: [[false, "list"], [false, "form"]],
            domain: [["id", "in", subordinateIds]],
            target: "current",
        });
    }

    _onOpenPopover() {
        // zostawione puste na ten etap
    }
}

export const customHrOrgChartField = {
    component: CustomHrOrgChart,
};

registry.category("fields").add("custom_hr_org_chart", customHrOrgChartField);