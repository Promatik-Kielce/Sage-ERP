TARGET_XMLIDS = [
    "hr_attendance.view_hr_hours_balance_adjustment_form",
    "hr_attendance.view_hr_hours_balance_adjustment_tree",
    "hr_attendance.menu_hr_hours_balance_adjustment",
    "hr_attendance.view_hr_hours_balance_adjustment_wizard_form",
    "hr_attendance.hr_employee_hours_balance_line_view_list",
    "hr_attendance.hr_employee_hours_balance_line_view_graph_daily",
    "hr_attendance.hr_employee_hours_balance_line_view_graph_cumulative",
    "hr_attendance.hr_employee_hours_balance_line_view_graph_comparison",
    "hr_attendance.hr_employee_hours_balance_line_view_pivot",
]

TARGET_TOKENS = (
    "action_view_hours_balance_detail",
    "action_adjust_hours_balance",
    "action_view_hours_balance_adjustments",
    "hours_balance",
    "hours_balance_adjustment_ids",
    "hours_balance_adjustment_count",
    "hours_balance_start_date",
)

def post_init_hook(env):
    for xmlid in TARGET_XMLIDS:
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec and "active" in rec._fields:
            rec.write({"active": False})

    views = env["ir.ui.view"].with_context(active_test=False).search([
        ("model", "in", ["hr.employee", "hr.employee.public"]),
    ])
    target_views = views.filtered(
        lambda v: any(token in (v.arch_db or "") for token in TARGET_TOKENS)
    )
    if target_views:
        target_views.write({"active": False})

    menus = env["ir.ui.menu"].with_context(active_test=False).search([])
    target_menus = menus.filtered(
        lambda m: any(token in (m.name or "").lower() for token in (
            "hours balance",
            "adjust balance",
            "balance adjustments",
        ))
    )
    if target_menus:
        target_menus.write({"active": False})

