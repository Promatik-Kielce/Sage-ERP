{
    "name": "HR Multi Manager",
    "version": "19.0.1.0.0",
    "summary": "Multiple managers for employees",
    "category": "Human Resources",
    "author": "Your Company",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "web",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_employee_views.xml",
        "views/hr_employee_manager_rel_views.xml",
        "views/hr_org_chart_menu.xml",
        "views/hr_multi_org_chart_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "custom_hr_manager_multi_approver/static/src/multi_org_chart/*.js",
            "custom_hr_manager_multi_approver/static/src/multi_org_chart/*.xml",
            "custom_hr_manager_multi_approver/static/src/multi_org_chart/*.scss",
        ],
    },
    "installable": True,
    "application": False,
}