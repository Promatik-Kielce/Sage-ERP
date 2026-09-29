from odoo import models
from odoo.fields import Domain


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def _get_officer_employee_domain(self):
        return super()._get_officer_employee_domain() | Domain("x_is_managed_by_me", "=", True)
