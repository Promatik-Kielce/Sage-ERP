from odoo import api, fields, models
from markupsafe import Markup, escape


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    manager_relation_ids = fields.One2many(
        "hr.employee.manager.rel",
        "employee_id",
        string="Manager Relations",
    )

    x_manager_ids = fields.Many2many(
        "hr.employee",
        "hr_employee_all_manager_rel",
        "employee_id",
        "manager_id",
        compute="_compute_x_manager_ids",
        string="All Managers",
        compute_sudo=True,
        store=True,
    )

    x_primary_manager_id = fields.Many2one(
        "hr.employee",
        compute="_compute_x_primary_manager_id",
        string="Primary Manager (Computed)",
        compute_sudo=True,
        store=True,
    )

    x_multi_org_chart_html = fields.Html(
        string="Multi Organization Chart",
        compute="_compute_x_multi_org_chart_html",
        sanitize=False,
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

    @api.depends(
        "name",
        "job_title",
        "manager_relation_ids.active",
        "manager_relation_ids.is_primary",
        "manager_relation_ids.sequence",
        "manager_relation_ids.manager_id",
        "manager_relation_ids.manager_id.name",
        "manager_relation_ids.manager_id.job_title",
    )
    def _compute_x_multi_org_chart_html(self):
        for employee in self:
            rels = employee.manager_relation_ids.filtered(
                lambda r: r.active and r.manager_id
            ).sorted(key=lambda r: (not r.is_primary, r.sequence, r.id))

            if not rels:
                employee.x_multi_org_chart_html = Markup(
                    """
                    <div class="x_odoo_org_chart">
                        <div class="x_odoo_org_chart_head">
                            <div class="x_odoo_org_chart_title">ORGANIZATION CHART</div>
                        </div>
                        <div class="x_odoo_org_chart_empty">No managers assigned.</div>
                    </div>
                    """
                )
                continue

            manager_cards = []
            for rel in rels:
                manager = rel.manager_id
                badge = "primary" if rel.is_primary else "manager"
                manager_cards.append(
                    f"""
                    <div class="x_odoo_org_manager_col">
                        <div class="x_odoo_org_card x_odoo_org_card_manager {'x_odoo_org_card_primary' if rel.is_primary else ''}">
                            <div class="x_odoo_org_avatar">{escape((manager.name or '?')[:1].upper())}</div>
                            <div class="x_odoo_org_text">
                                <div class="x_odoo_org_name">{escape(manager.name or '')}</div>
                                <div class="x_odoo_org_job">{escape(manager.job_title or '')}</div>
                            </div>
                        </div>
                        <div class="x_odoo_org_badge">{badge}</div>
                    </div>
                    """
                )

            employee_html = f"""
                <div class="x_odoo_org_employee_wrap">
                    <div class="x_odoo_org_vline"></div>
                    <div class="x_odoo_org_card x_odoo_org_card_employee">
                        <div class="x_odoo_org_avatar">{escape((employee.name or '?')[:1].upper())}</div>
                        <div class="x_odoo_org_text">
                            <div class="x_odoo_org_name">{escape(employee.name or '')}</div>
                            <div class="x_odoo_org_job">{escape(employee.job_title or '')}</div>
                        </div>
                    </div>
                </div>
            """

            html = f"""
                <div class="x_odoo_org_chart">
                    <div class="x_odoo_org_chart_head">
                        <div class="x_odoo_org_chart_title">ORGANIZATION CHART</div>
                    </div>
                    <div class="x_odoo_org_managers_row">
                        {''.join(manager_cards)}
                    </div>
                    <div class="x_odoo_org_hline_wrap">
                        <div class="x_odoo_org_hline"></div>
                    </div>
                    {employee_html}
                </div>
            """
            employee.x_multi_org_chart_html = Markup(html)

    def get_manager_relations(self):
        self.ensure_one()
        return self.manager_relation_ids.filtered(lambda r: r.active and r.manager_id)

    def get_manager_employees(self):
        self.ensure_one()
        return self.get_manager_relations().mapped("manager_id")

    def get_primary_manager(self):
        self.ensure_one()
        rel = self.get_manager_relations().filtered(lambda r: r.is_primary)[:1]
        return rel.manager_id or False

    def _sync_parent_id_from_manager_relations(self):
        for employee in self:
            primary_manager = employee.get_primary_manager()
            new_parent_id = primary_manager.id if primary_manager else False
            super(HrEmployee, employee.with_context(skip_manager_rel_sync=True)).write({
                "parent_id": new_parent_id,
            })

    def action_open_multi_org_chart(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "custom_hr_multi_org_chart",
            "name": "Multi Org Chart",
            "context": {"default_employee_id": self.id},
        }

    @api.model
    def get_multi_org_chart_data(self, employee_id=False):
        Employee = self.env["hr.employee"].sudo()

        if employee_id:
            root = Employee.browse(employee_id).exists()
        else:
            root = Employee.search([("parent_id", "=", False)], limit=1)

        if not root:
            return {}

        def build_node(emp, visited=None):
            visited = visited or set()
            if emp.id in visited:
                return {
                    "id": emp.id,
                    "name": emp.name,
                    "job_title": emp.job_title or "",
                    "managers": [],
                    "children": [],
                    "cycle": True,
                }

            visited = set(visited)
            visited.add(emp.id)
            direct_children = Employee.search([("parent_id", "=", emp.id)])
            managers = emp.get_manager_employees()

            return {
                "id": emp.id,
                "name": emp.name,
                "job_title": emp.job_title or "",
                "work_email": emp.work_email or "",
                "parent_id": emp.parent_id.id or False,
                "primary_manager_id": emp.x_primary_manager_id.id or False,
                "managers": [
                    {"id": m.id, "name": m.name, "job_title": m.job_title or ""}
                    for m in managers
                ],
                "children": [build_node(child, visited) for child in direct_children],
            }

        return build_node(root)