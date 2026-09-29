from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _clean_attendance_officers(self):
        # Keep the officer group for users who still manage someone (primary or not).
        relations = self.env["hr.employee.manager.rel"].sudo().search([
            ("manager_id.user_id", "in", self.ids),
        ])
        subordinates = self.env["hr.employee"].sudo().search([
            ("parent_id.user_id", "in", self.ids),
        ])
        still_managing = relations.manager_id.user_id | subordinates.parent_id.user_id
        return super(ResUsers, self - still_managing)._clean_attendance_officers()
