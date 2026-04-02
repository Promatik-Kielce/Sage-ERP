from odoo import models, _
from odoo.exceptions import AccessError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _compute_hours_balance(self):
        for employee in self:
            employee.hours_balance = 0.0

    def _compute_hours_balance_adjustment_count(self):
        for employee in self:
            employee.hours_balance_adjustment_count = 0

    def _compute_hours_balance_value(self):
        self.ensure_one()
        return 0.0

    def action_view_hours_balance_detail(self):
        raise AccessError(_("Hours Balance is disabled."))

    def action_adjust_hours_balance(self):
        raise AccessError(_("Adjust Balance is disabled."))

    # Nazwa bardzo prawdopodobna na podstawie Twojego grep.
    # Jeśli w Twoim pliku metoda nazywa się inaczej, zmień tylko nazwę tej funkcji.
    def action_view_hours_balance_adjustments(self):
        raise AccessError(_("Balance Adjustments are disabled."))