from odoo import api, models


class HrLeave(models.Model):
    _inherit = "hr.leave"

    def _compute_can_approve(self):
        super()._compute_can_approve()
        for leave in self:
            if leave.employee_id and leave.employee_id.is_leave_approver_user(self.env.user):
                leave.can_approve = True

    def _compute_can_validate(self):
        super()._compute_can_validate()
        for leave in self:
            if leave.employee_id and leave.employee_id.is_leave_approver_user(self.env.user):
                leave.can_validate = True

    def _compute_can_refuse(self):
        super()._compute_can_refuse()
        for leave in self:
            if leave.employee_id and leave.employee_id.is_leave_approver_user(self.env.user):
                leave.can_refuse = True

    def _compute_can_cancel(self):
        super()._compute_can_cancel()
        for leave in self:
            if leave.employee_id and leave.employee_id.is_leave_approver_user(self.env.user):
                leave.can_cancel = True

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        for leave in leaves:
            approver_partners = leave.employee_id.get_leave_approver_users().mapped("partner_id")
            if approver_partners:
                leave.message_subscribe(partner_ids=approver_partners.ids)
        return leaves