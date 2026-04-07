from odoo import api, fields, models


class HrEmployeeLeaveApproverRel(models.Model):
    _name = "hr.employee.leave.approver.rel"
    _description = "Employee Leave Approver Relation"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        ondelete="cascade",
        index=True,
    )

    user_id = fields.Many2one(
        "res.users",
        string="Approver",
        required=True,
        ondelete="cascade",
        index=True,
    )

    is_primary = fields.Boolean(
        string="Primary Approver",
        default=False,
        help="Primary leave approver used to synchronize leave_manager_id.",
    )

    _sql_constraints = [
        (
            "employee_leave_approver_unique",
            "unique(employee_id, user_id)",
            "This leave approver is already linked to the employee.",
        ),
    ]

    def _unset_other_primary_approvers(self):
        for rec in self.filtered(lambda r: r.employee_id and r.is_primary and r.active):
            others = self.search([
                ("id", "!=", rec.id),
                ("employee_id", "=", rec.employee_id.id),
                ("is_primary", "=", True),
                ("active", "=", True),
            ])
            if others:
                others.write({"is_primary": False})

    def _ensure_one_primary_if_possible(self):
        for employee in self.mapped("employee_id"):
            active_rels = employee.leave_approver_relation_ids.filtered(lambda r: r.active and r.user_id)
            if active_rels and not active_rels.filtered(lambda r: r.is_primary):
                active_rels[:1].write({"is_primary": True})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        primary_records = records.filtered(lambda r: r.is_primary and r.active)
        if primary_records:
            primary_records._unset_other_primary_approvers()

        records._ensure_one_primary_if_possible()
        records.mapped("employee_id")._sync_leave_manager_id_from_relations()
        return records

    def write(self, vals):
        employees_before = self.mapped("employee_id")

        if vals.get("is_primary"):
            for rec in self:
                if rec.employee_id:
                    others = self.search([
                        ("id", "!=", rec.id),
                        ("employee_id", "=", rec.employee_id.id),
                        ("is_primary", "=", True),
                        ("active", "=", True),
                    ])
                    if others:
                        others.write({"is_primary": False})

        res = super().write(vals)

        employees_after = self.mapped("employee_id")
        employees = employees_before | employees_after

        employees.leave_approver_relation_ids._ensure_one_primary_if_possible()
        employees._sync_leave_manager_id_from_relations()
        return res

    def unlink(self):
        employees = self.mapped("employee_id")
        res = super().unlink()

        employees.leave_approver_relation_ids._ensure_one_primary_if_possible()
        employees._sync_leave_manager_id_from_relations()
        return res