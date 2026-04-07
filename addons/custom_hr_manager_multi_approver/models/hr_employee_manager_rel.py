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
        help="Primary manager used to synchronize the standard Manager field.",
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

    def _unset_other_primary_managers(self):
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
            active_rels = employee.manager_relation_ids.filtered(lambda r: r.active and r.manager_id)
            if active_rels and not active_rels.filtered(lambda r: r.is_primary):
                active_rels[:1].write({"is_primary": True})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        # Jeśli dodano rekord jako primary, zdejmij primary z pozostałych
        primary_records = records.filtered(lambda r: r.is_primary and r.active)
        if primary_records:
            primary_records._unset_other_primary_managers()

        # Jeśli pracownik nie ma żadnego primary, ustaw pierwszy aktywny
        records._ensure_one_primary_if_possible()

        records.mapped("employee_id")._sync_parent_id_from_manager_relations()
        return records

    def write(self, vals):
        employees_before = self.mapped("employee_id")

        # Jeśli ten rekord ma stać się primary, najpierw zdejmij primary z pozostałych
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

        employees.manager_relation_ids._ensure_one_primary_if_possible()
        employees._sync_parent_id_from_manager_relations()
        return res

    def unlink(self):
        employees = self.mapped("employee_id")
        res = super().unlink()

        employees.manager_relation_ids._ensure_one_primary_if_possible()
        employees._sync_parent_id_from_manager_relations()
        return res