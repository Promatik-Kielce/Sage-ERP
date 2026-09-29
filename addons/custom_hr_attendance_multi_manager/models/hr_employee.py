from odoo import models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def write(self, vals):
        res = super().write(vals)
        if "user_id" in vals:
            # A manager employee just got linked to a user: give that user the officer group.
            self.env["hr.employee.manager.rel"].sudo().search([
                ("manager_id", "in", self.ids),
            ])._grant_attendance_officer_group()
        return res
