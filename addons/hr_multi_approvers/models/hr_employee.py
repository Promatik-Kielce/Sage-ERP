from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    manager_relation_ids = fields.One2many(
        "hr.employee.manager.rel",
        "employee_id",
        string="Manager Relations",
    )

    x_manager_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_x_manager_ids",
        string="All Managers",
        compute_sudo=True,
    )

    x_primary_manager_id = fields.Many2one(
        "hr.employee",
        compute="_compute_x_primary_manager_id",
        string="Primary Manager (Computed)",
    )

    leave_approver_relation_ids = fields.One2many(
        "hr.employee.leave.approver.rel",
        "employee_id",
        string="Leave Approver Relations",
    )

    x_leave_approver_ids = fields.Many2many(
        "res.users",
        compute="_compute_x_leave_approver_ids",
        string="Time Off Approvers",
        compute_sudo=True,
    )

    x_primary_leave_approver_id = fields.Many2one(
        "res.users",
        compute="_compute_x_primary_leave_approver_id",
        string="Primary Time Off Approver",
    )

    @api.depends("manager_relation_ids.active", "manager_relation_ids.manager_id")
    def _compute_x_manager_ids(self):
        for employee in self:
            employee.x_manager_ids = employee.manager_relation_ids.filtered(
                lambda r: r.active and r.manager_id
            ).mapped("manager_id")

    @api.depends(
        "manager_relation_ids.active",
        "manager_relation_ids.is_primary",
        "manager_relation_ids.manager_id",
    )
    def _compute_x_primary_manager_id(self):
        for employee in self:
            rel = employee.manager_relation_ids.filtered(
                lambda r: r.active and r.is_primary and r.manager_id
            )[:1]
            employee.x_primary_manager_id = rel.manager_id or False

    @api.depends("leave_approver_relation_ids.active", "leave_approver_relation_ids.user_id")
    def _compute_x_leave_approver_ids(self):
        for employee in self:
            employee.x_leave_approver_ids = employee.leave_approver_relation_ids.filtered(
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

    def get_manager_relations(self):
        self.ensure_one()
        return self.manager_relation_ids.filtered(lambda r: r.active and r.manager_id)

    def get_manager_employees(self):
        self.ensure_one()
        return self.get_manager_relations().mapped("manager_id")

    def get_manager_users(self):
        self.ensure_one()
        return self.get_manager_employees().mapped("user_id")

    def get_primary_manager(self):
        self.ensure_one()
        rel = self.get_manager_relations().filtered(lambda r: r.is_primary)[:1]
        return rel.manager_id

    def get_leave_approver_relations(self):
        self.ensure_one()
        return self.leave_approver_relation_ids.filtered(lambda r: r.active and r.user_id)

    def get_leave_approver_users(self):
        self.ensure_one()
        return self.get_leave_approver_relations().mapped("user_id")

    def get_primary_leave_approver(self):
        self.ensure_one()
        rel = self.get_leave_approver_relations().filtered(lambda r: r.is_primary)[:1]
        return rel.user_id

    def is_leave_approver_user(self, user):
        self.ensure_one()
        return user in self.get_leave_approver_users()

    def _sync_parent_id_from_manager_relations(self):
        for employee in self:
            primary_manager = employee.get_primary_manager()
            new_parent_id = primary_manager.id if primary_manager else False
            if employee.parent_id.id != new_parent_id:
                super(HrEmployee, employee).write({"parent_id": new_parent_id})

    def _sync_leave_manager_id_from_relations(self):
        for employee in self:
            primary_user = employee.get_primary_leave_approver()
            new_user_id = primary_user.id if primary_user else False
            if employee.leave_manager_id.id != new_user_id:
                super(HrEmployee, employee).write({"leave_manager_id": new_user_id})

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees._sync_parent_id_from_manager_relations()
        employees._sync_leave_manager_id_from_relations()
        return employees

    def write(self, vals):
        res = super().write(vals)
        if "manager_relation_ids" in vals:
            self._sync_parent_id_from_manager_relations()
        if "leave_approver_relation_ids" in vals:
            self._sync_leave_manager_id_from_relations()
        return res

    def action_debug_managers(self):
        self.ensure_one()
        primary_manager = self.get_primary_manager()
        primary_leave = self.get_primary_leave_approver()
        return {
            "parent_id": self.parent_id.name or False,
            "primary": primary_manager.name or False,
            "all": self.get_manager_employees().mapped("name"),
            "leave_manager_id": self.leave_manager_id.name or False,
            "primary_leave_approver": primary_leave.name or False,
            "all_leave_approvers": self.get_leave_approver_users().mapped("name"),
        }