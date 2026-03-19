from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
        domain="[('share', '=', False)]",
    )

    is_primary = fields.Boolean(
        string="Primary Approver",
        default=False,
    )

    _sql_constraints = [
        (
            "employee_leave_approver_unique",
            "unique(employee_id, user_id)",
            "This leave approver is already linked to the employee.",
        ),
    ]

    @api.constrains("employee_id", "user_id")
    def _check_employee_not_own_approver_user(self):
        for rec in self:
            if rec.employee_id.user_id and rec.employee_id.user_id == rec.user_id:
                raise ValidationError("Employee cannot be their own leave approver.")