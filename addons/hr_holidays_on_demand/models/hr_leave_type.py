from datetime import date

from odoo import api, fields, models
from odoo.tools.translate import _


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    allows_on_demand = fields.Boolean(
        string='Allow On-Demand Leave',
        default=False,
        help="If checked, employees can flag individual leave requests as 'on demand' (na żądanie). "
             "These are drawn from the same paid time off pool but limited per calendar year.",
    )
    on_demand_limit = fields.Integer(
        string='On-Demand Days Limit (per year)',
        default=4,
        help="Maximum on-demand days allowed per calendar year (Polish law: 4 days).",
    )

    def _get_on_demand_taken(self, employee_ids, year=None):
        """Return dict {(employee_id, leave_type_id): days_taken} for on-demand leaves."""
        if year is None:
            year = fields.Date.today().year
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        on_demand_types = self.filtered(lambda lt: lt.allows_on_demand)
        if not on_demand_types or not employee_ids:
            return {}

        results = self.env['hr.leave']._read_group(
            domain=[
                ('holiday_status_id', 'in', on_demand_types.ids),
                ('employee_id', 'in', employee_ids),
                ('is_on_demand', '=', True),
                ('state', 'in', ['confirm', 'validate1', 'validate']),
                ('request_date_from', '>=', year_start),
                ('request_date_from', '<=', year_end),
            ],
            groupby=['employee_id', 'holiday_status_id'],
            aggregates=['number_of_days:sum'],
        )
        return {
            (employee.id, leave_type.id): days_sum or 0.0
            for employee, leave_type, days_sum in results
        }

    def get_allocation_data(self, employees, target_date=None):
        allocation_data = super().get_allocation_data(employees, target_date)

        on_demand_types = self.filtered(lambda lt: lt.allows_on_demand)
        if not on_demand_types:
            return allocation_data

        on_demand_map = self._get_on_demand_taken(employees.ids)

        for employee in employees:
            for lt_info in allocation_data[employee]:
                lt_id = lt_info[3]
                leave_type = self.browse(lt_id)
                if not leave_type.allows_on_demand:
                    continue
                taken = on_demand_map.get((employee.id, lt_id), 0.0)
                lt_info[1]['on_demand_taken'] = round(taken, 2)
                lt_info[1]['on_demand_limit'] = leave_type.on_demand_limit
                lt_info[1]['on_demand_remaining'] = max(0.0, leave_type.on_demand_limit - taken)

        return allocation_data

    @api.depends('requires_allocation', 'virtual_remaining_leaves', 'max_leaves', 'request_unit',
                 'allows_on_demand', 'on_demand_limit')
    @api.depends_context('holiday_status_display_name', 'employee_id')
    def _compute_display_name(self):
        super()._compute_display_name()
        if not self.requested_display_name():
            return

        on_demand_types = self.filtered(
            lambda lt: lt.allows_on_demand and lt.requires_allocation
        )
        if not on_demand_types:
            return

        employee_id = (
            self.env.context.get('employee_id')
            or self.env.context.get('default_employee_id')
        )
        if not employee_id:
            return

        on_demand_map = on_demand_types._get_on_demand_taken([employee_id])

        for record in on_demand_types:
            taken = on_demand_map.get((employee_id, record.id), 0.0)
            on_demand_remaining = max(0, record.on_demand_limit - taken)
            record.display_name = _(
                "%(base)s, incl. %(remaining)g on demand",
                base=record.display_name,
                remaining=on_demand_remaining,
            )
