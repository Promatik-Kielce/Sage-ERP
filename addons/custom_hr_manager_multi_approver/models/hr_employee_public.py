from odoo import fields, models


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    # Needed on the public model too: hr.employee searches made by non-HR users
    # are redirected to hr.employee.public.
    x_is_managed_by_me = fields.Boolean(
        string="Managed by Me",
        compute="_compute_x_is_managed_by_me",
        search="_search_x_is_managed_by_me",
    )

    def _compute_x_is_managed_by_me(self):
        managed_ids = set(self.env["hr.employee"]._get_x_managed_employee_ids())
        for employee in self:
            employee.x_is_managed_by_me = employee.id in managed_ids

    def _search_x_is_managed_by_me(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        return [("id", operator, self.env["hr.employee"]._get_x_managed_employee_ids())]
