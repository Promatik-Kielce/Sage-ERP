from odoo import api, models


class HrEmployeeManagerRel(models.Model):
    _inherit = "hr.employee.manager.rel"

    def _grant_attendance_officer_group(self):
        """Give every active manager's user the attendance officer group.

        The officer record rules then restrict them to their own employees.
        The group is only ever added here, never removed.
        """
        officer_group = self.env.ref("hr_attendance.group_hr_attendance_officer", raise_if_not_found=False)
        if not officer_group:
            return
        users = self.sudo().filtered("active").manager_id.user_id.filtered(
            lambda user: not user.share and not user.has_group("hr_attendance.group_hr_attendance_officer")
        )
        if users:
            users.write({"group_ids": [(4, officer_group.id)]})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._grant_attendance_officer_group()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "manager_id" in vals or "active" in vals:
            self._grant_attendance_officer_group()
        return res
