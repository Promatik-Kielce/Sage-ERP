from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    leave_approver_relation_ids = fields.One2many(
        "hr.employee.leave.approver.rel",
        "employee_id",
        string="Leave Approver Relations",
    )

    leave_manager_ids = fields.Many2many(
        "res.users",
        "hr_employee_leave_manager_rel",
        "employee_id",
        "user_id",
        compute="_compute_leave_manager_ids",
        string="Time Off Approvers",
        compute_sudo=True,
        store=True,
    )

    x_primary_leave_approver_id = fields.Many2one(
        "res.users",
        compute="_compute_x_primary_leave_approver_id",
        string="Primary Time Off Approver",
        compute_sudo=True,
        store=True,
    )

    @api.depends("leave_approver_relation_ids.active", "leave_approver_relation_ids.user_id")
    def _compute_leave_manager_ids(self):
        for employee in self:
            employee.leave_manager_ids = employee.leave_approver_relation_ids.filtered(
                lambda r: r.active and r.user_id
            ).mapped("user_id")

    @api.depends(
        "leave_approver_relation_ids.active",
        "leave_approver_relation_ids.is_primary",
        "leave_approver_relation_ids.user_id",
    )
    def _compute_x_primary_leave_approver_id(self):
        for employee in self:
            rel = employee.leave_approver_relation_ids.filtered(
                lambda r: r.active and r.is_primary and r.user_id
            )[:1]
            employee.x_primary_leave_approver_id = rel.user_id or False

    def get_leave_approver_relations(self):
        self.ensure_one()
        return self.leave_approver_relation_ids.filtered(lambda r: r.active and r.user_id)

    def get_leave_approver_users(self):
        self.ensure_one()
        return self.get_leave_approver_relations().mapped("user_id")

    def get_primary_leave_approver(self):
        self.ensure_one()
        rel = self.get_leave_approver_relations().filtered(lambda r: r.is_primary)[:1]
        return rel.user_id or False

    def _is_user_leave_approver(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        return user in self.get_leave_approver_users()

    def _sync_leave_manager_id_from_relations(self):
        for employee in self:
            primary_user = employee.get_primary_leave_approver()
            new_user_id = primary_user.id if primary_user else False

            super(HrEmployee, employee.with_context(skip_leave_rel_sync=True)).write({
                "leave_manager_id": new_user_id,
            })