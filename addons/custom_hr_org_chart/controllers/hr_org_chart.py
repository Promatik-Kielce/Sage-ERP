# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class CustomHrOrgChartController(http.Controller):

    def _get_employee(self, employee_id, **kw):
        employee_id = int(employee_id) if employee_id else False

        context = kw.get("context", request.env.context)
        if "allowed_company_ids" in context:
            cids = context["allowed_company_ids"]
        else:
            cids = [request.env.company.id]

        Employee = request.env["hr.employee.public"].with_context(allowed_company_ids=cids)
        employee = Employee.browse(employee_id)
        return employee if employee.has_access("read") else Employee.browse()

    def _get_real_employee(self, employee_public):
        if not employee_public:
            return request.env["hr.employee"]
        return request.env["hr.employee"].sudo().browse(employee_public.id).exists()

    def _prepare_employee_data(self, employee):
        job = employee.sudo().job_id
        return dict(
            id=employee.id,
            name=employee.name,
            link="/mail/view?model=%s&res_id=%s" % ("hr.employee.public", employee.id),
            job_id=job.id,
            job_name=job.name or "",
            direct_sub_count=len(employee.child_ids - employee),
            indirect_sub_count=employee.child_all_count,
        )

    def _get_multi_managers_public(self, employee_public):
        employee = self._get_real_employee(employee_public)
        if not employee:
            return request.env["hr.employee.public"]

        relations = employee.manager_relation_ids.filtered(
            lambda r: r.active and r.manager_id
        ).sorted(key=lambda r: (not r.is_primary, r.sequence, r.id))

        if not relations:
            return request.env["hr.employee.public"]

        manager_ids = relations.mapped("manager_id").ids
        return request.env["hr.employee.public"].sudo().browse(manager_ids).exists()

    def _get_multi_children_public(self, employee_public):
        """
        Zwraca wszystkich pracowników, dla których bieżący employee jest managerem:
        - primary (przez parent_id / child_ids)
        - secondary (przez manager_relation_ids.manager_id)
        """
        employee = self._get_real_employee(employee_public)
        if not employee:
            return request.env["hr.employee.public"]

        # standardowe dzieci po parent_id
        primary_children = employee.child_ids.filtered(lambda e: e != employee)

        # dodatkowe dzieci po relacji multi-manager
        relation_children = request.env["hr.employee"].sudo().search([
            ("manager_relation_ids.manager_id", "=", employee.id),
            ("manager_relation_ids.active", "=", True),
        ])

        all_children = (primary_children | relation_children).filtered(lambda e: e != employee)

        return request.env["hr.employee.public"].sudo().browse(all_children.ids).exists()

    @http.route("/hr/get_redirect_model", type="jsonrpc", auth="user")
    def get_redirect_model(self):
        if request.env["hr.employee"].has_access("read"):
            return "hr.employee"
        return "hr.employee.public"

    @http.route("/hr/get_multi_org_chart", type="jsonrpc", auth="user")
    def get_multi_org_chart(self, employee_id, new_parent_id=None, **kw):
        employee_public = self._get_employee(employee_id, **kw)
        new_parent_public = self._get_employee(new_parent_id, **kw)

        if not employee_public:
            return {
                "self": {},
                "managers": [],
                "managers_more": False,
                "children": [],
            }

        # managers
        if new_parent_id is not None and new_parent_public:
            managers_public = request.env["hr.employee.public"].sudo().browse([new_parent_public.id])
            managers_more = False
        else:
            managers_public = self._get_multi_managers_public(employee_public)
            managers_more = len(managers_public) > 5

        # children: primary + secondary
        children_public = self._get_multi_children_public(employee_public)

        return {
            "self": self._prepare_employee_data(employee_public),
            "managers": [
                self._prepare_employee_data(manager)
                for manager in managers_public[:5]
            ],
            "managers_more": managers_more,
            "children": [
                self._prepare_employee_data(child)
                for child in children_public
            ],
        }

    @http.route("/hr/get_multi_org_chart_full", type="jsonrpc", auth="user")
    def get_multi_org_chart_full(self, employee_id=None, **kw):
        Employee = request.env["hr.employee"].sudo()

        employee = Employee.browse(int(employee_id)) if employee_id else Employee.browse()
        employee = employee.exists()

        if not employee:
            return {
                "root": None,
                "employees": [],
            }

        # root po primary chain
        root = employee
        visited = request.env["hr.employee"]
        while root.parent_id and root.parent_id not in visited:
            visited |= root
            root = root.parent_id

        subtree = request.env["hr.employee"]

        def collect(node):
            nonlocal subtree
            if node in subtree:
                return
            subtree |= node

            # primary children
            direct_children = node.child_ids

            # secondary children
            relation_children = request.env["hr.employee"].sudo().search([
                ("manager_relation_ids.manager_id", "=", node.id),
                ("manager_relation_ids.active", "=", True),
            ])

            for child in (direct_children | relation_children):
                collect(child)

        collect(root)

        def prepare_node(emp):
            return {
                "id": emp.id,
                "name": emp.name,
                "job_title": emp.job_title or "",
                "work_email": emp.work_email or "",
                "parent_id": emp.parent_id.id or False,
                "primary_manager_id": emp.x_primary_manager_id.id or False,
                "managers": [
                    {
                        "id": rel.manager_id.id,
                        "name": rel.manager_id.name,
                        "job_title": rel.manager_id.job_title or "",
                        "is_primary": rel.is_primary,
                        "sequence": rel.sequence,
                    }
                    for rel in emp.manager_relation_ids.filtered(
                        lambda r: r.active and r.manager_id
                    ).sorted(key=lambda r: (not r.is_primary, r.sequence, r.id))
                ],
                "children_ids": list({
                    *emp.child_ids.ids,
                    *request.env["hr.employee"].sudo().search([
                        ("manager_relation_ids.manager_id", "=", emp.id),
                        ("manager_relation_ids.active", "=", True),
                    ]).ids,
                }),
            }

        return {
            "root": root.id,
            "focus_employee_id": employee.id,
            "employees": [
                prepare_node(emp)
                for emp in subtree.sorted(key=lambda e: (e.parent_id.id or 0, e.name or ""))
            ],
        }

    @http.route("/hr/get_subordinates", type="jsonrpc", auth="user")
    def get_subordinates(self, employee_id, subordinates_type=None, **kw):
        employee_public = self._get_employee(employee_id, **kw)
        if not employee_public:
            return {}

        employee = self._get_real_employee(employee_public)
        if not employee:
            return []

        primary_children = employee.child_ids
        relation_children = request.env["hr.employee"].sudo().search([
            ("manager_relation_ids.manager_id", "=", employee.id),
            ("manager_relation_ids.active", "=", True),
        ])

        all_direct = (primary_children | relation_children).filtered(lambda e: e != employee)

        if subordinates_type == "direct":
            return all_direct.ids

        # uproszczony fallback dla indirect/total
        if subordinates_type in ("indirect", "total", None):
            visited = request.env["hr.employee"]

            def collect(node):
                nonlocal visited
                if node in visited:
                    return
                visited |= node
                node_primary = node.child_ids
                node_secondary = request.env["hr.employee"].sudo().search([
                    ("manager_relation_ids.manager_id", "=", node.id),
                    ("manager_relation_ids.active", "=", True),
                ])
                for child in (node_primary | node_secondary):
                    collect(child)

            for child in all_direct:
                collect(child)

            if subordinates_type == "indirect":
                return (visited - all_direct).ids

            return visited.ids

        return all_direct.ids