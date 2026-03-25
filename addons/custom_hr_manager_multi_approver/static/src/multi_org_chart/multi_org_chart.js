/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class MultiOrgChart extends Component {
    static template = "custom_hr_manager_multi_approver.MultiOrgChart";

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            data: null,
            loading: true,
        });

        onWillStart(async () => {
            const employeeId = this.props.action?.context?.default_employee_id || false;
            const result = await this.orm.call(
                "hr.employee",
                "get_multi_org_chart_data",
                [employeeId]
            );
            this.state.data = result;
            this.state.loading = false;
        });
    }
}

registry.category("actions").add("custom_hr_multi_org_chart", MultiOrgChart);