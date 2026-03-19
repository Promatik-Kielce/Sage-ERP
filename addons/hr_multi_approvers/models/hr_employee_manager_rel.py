from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrEmployeeManagerRel(models.Model):
    _name = "hr.employee.manager.rel"
    _description = "Employee Manager Relation"
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

    manager_id = fields.Many2one(
        "hr.employee",
        string="Manager",
        required=True,
        ondelete="cascade",
        index=True,
        domain="[('id', '!=', employee_id)]",
    )

    is_primary = fields.Boolean(
        string="Primary Manager",
        default=False,
        help="Primary manager used to synchronize the standard Manager field (parent_id).",
    )

    _sql_constraints = [
        (
            "employee_manager_unique",
            "unique(employee_id, manager_id)",
            "This manager is already linked to the employee.",
        ),
    ]

    @api.constrains("employee_id", "manager_id")
    def _check_employee_not_own_manager(self):
        for rec in self:
            if rec.employee_id and rec.manager_id and rec.employee_id == rec.manager_id:
                raise ValidationError("An employee cannot be their own manager.")

    @api.constrains("employee_id", "is_primary", "active")
    def _check_only_one_primary_manager(self):
        for rec in self:
            if not rec.active or not rec.is_primary or not rec.employee_id:
                continue
            others = self.search_count([
                ("id", "!=", rec.id),
                ("employee_id", "=", rec.employee_id.id),
                ("is_primary", "=", True),
                ("active", "=", True),
            ])
            if others:
                raise ValidationError("Only one active primary manager is allowed per employee.")