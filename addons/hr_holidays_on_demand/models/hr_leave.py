from datetime import date

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    is_on_demand = fields.Boolean(
        string='On Demand',
        default=False,
        tracking=True,
        help="Check if this leave request is 'on demand' (na żądanie). "
             "Limited per calendar year under Polish labor law.",
    )
    holiday_status_allows_on_demand = fields.Boolean(
        related='holiday_status_id.allows_on_demand',
        string='Leave Type Allows On Demand',
    )

    @api.constrains('is_on_demand', 'holiday_status_id', 'employee_id', 'number_of_days')
    def _check_on_demand_limit(self):
        for leave in self.filtered(lambda l: l.is_on_demand and l.state not in ('refuse', 'cancel')):
            if not leave.holiday_status_id.allows_on_demand:
                raise ValidationError(
                    _("Leave type '%(type)s' does not allow on-demand leaves.",
                      type=leave.holiday_status_id.name)
                )
            year = leave.request_date_from.year if leave.request_date_from else fields.Date.today().year
            year_start = date(year, 1, 1)
            year_end = date(year, 12, 31)

            other_on_demand_days = sum(
                self.env['hr.leave'].search([
                    ('id', '!=', leave._origin.id),
                    ('holiday_status_id', '=', leave.holiday_status_id.id),
                    ('employee_id', '=', leave.employee_id.id),
                    ('is_on_demand', '=', True),
                    ('state', 'in', ['confirm', 'validate1', 'validate']),
                    ('request_date_from', '>=', year_start),
                    ('request_date_from', '<=', year_end),
                ]).mapped('number_of_days')
            )
            total = other_on_demand_days + leave.number_of_days
            limit = leave.holiday_status_id.on_demand_limit
            if total > limit:
                raise ValidationError(
                    _("You have exceeded the on-demand leave limit of %(limit)s days for %(year)s. "
                      "Already used: %(taken)s days.",
                      limit=limit,
                      year=year,
                      taken=round(other_on_demand_days, 2))
                )

    @api.onchange('holiday_status_id')
    def _onchange_holiday_status_on_demand(self):
        if not self.holiday_status_id.allows_on_demand:
            self.is_on_demand = False
