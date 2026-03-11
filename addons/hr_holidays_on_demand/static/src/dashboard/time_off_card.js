import { patch } from "@web/core/utils/patch";
import { TimeOffCard, TimeOffCardPopover } from "@hr_holidays/dashboard/time_off_card";
import { formatNumber } from "@hr_holidays/views/hooks";

// Extend popover props to accept on-demand data
TimeOffCardPopover.props.push(
    "on_demand_limit?",
    "on_demand_remaining?",
    "on_demand_taken?",
);

// Patch TimeOffCard to pass on-demand props to popover
patch(TimeOffCard.prototype, {
    onClickInfo(ev) {
        const { data, holidayStatusId, employeeId } = this.props;
        this.popover.open(ev.target, {
            allocated: formatNumber(this.lang, data.max_leaves),
            accrual_bonus: formatNumber(this.lang, data.accrual_bonus),
            approved: formatNumber(this.lang, data.leaves_approved),
            planned: formatNumber(this.lang, data.leaves_requested),
            left: formatNumber(this.lang, data.virtual_remaining_leaves),
            warning: this.warning,
            closest: data.closest_allocation_duration,
            request_unit: data.request_unit,
            exceeding_duration: data.exceeding_duration,
            allows_negative: data.allows_negative,
            max_allowed_negative: data.max_allowed_negative,
            onClickNewAllocationRequest: this.newAllocationRequestFrom.bind(this),
            errorLeaves: this.errorLeaves,
            accrualExcess: this.getAccrualExcess(data),
            timeOffType: holidayStatusId,
            employeeId: employeeId,
            employeeCompany: data.employee_company,
            on_demand_limit: data.on_demand_limit,
            on_demand_remaining: data.on_demand_remaining,
            on_demand_taken: data.on_demand_taken,
        });
    },
});
