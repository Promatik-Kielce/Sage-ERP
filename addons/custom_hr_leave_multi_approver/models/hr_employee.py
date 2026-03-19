from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    leave_manager_ids = fields.Many2many(
        "res.users",
        "hr_employee_leave_manager_rel",
        "employee_id",
        "user_id",
        string="Time Off Approvers",
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
        help="All users allowed to approve this employee's time off.",
    )

    @api.onchange("leave_manager_id")
    def _onchange_leave_manager_id_sync_multi(self):
        """
        Gdy w formularzu ustawisz głównego approvera, dopisz go też do listy M2M.
        """
        for employee in self:
            if employee.leave_manager_id and employee.leave_manager_id not in employee.leave_manager_ids:
                employee.leave_manager_ids |= employee.leave_manager_id

    @api.constrains("leave_manager_id", "leave_manager_ids")
    def _check_primary_leave_manager_in_multi(self):
        """
        Standardowy leave_manager_id musi należeć do leave_manager_ids.
        Dzięki temu core nadal ma 'głównego' approvera, a rozszerzenie ma pełną listę.
        """
        for employee in self:
            if employee.leave_manager_id and employee.leave_manager_id not in employee.leave_manager_ids:
                raise ValidationError(
                    _("Primary Time Off Approver must also be included in Time Off Approvers.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Po utworzeniu pracownika pilnujemy spójności:
        jeśli ustawiono leave_manager_id, to dopisujemy go także do leave_manager_ids.
        """
        employees = super().create(vals_list)
        for employee in employees:
            if employee.leave_manager_id and employee.leave_manager_id not in employee.leave_manager_ids:
                employee.write({
                    "leave_manager_ids": [(4, employee.leave_manager_id.id)],
                })
        return employees

    def write(self, vals):
        """
        Po zapisie pilnujemy spójności danych:
        leave_manager_id zawsze ma być też obecny w leave_manager_ids.
        """
        res = super().write(vals)
        for employee in self:
            if employee.leave_manager_id and employee.leave_manager_id not in employee.leave_manager_ids:
                employee.write({
                    "leave_manager_ids": [(4, employee.leave_manager_id.id)],
                })
        return res

    def _is_user_leave_approver(self, user=None):
        """
        Centralny helper: sprawdza, czy user jest approverem urlopów dla tego pracownika.
        Uwzględnia zarówno standardowe leave_manager_id, jak i nowe leave_manager_ids.
        """
        self.ensure_one()
        user = user or self.env.user
        return user == self.leave_manager_id or user in self.leave_manager_ids