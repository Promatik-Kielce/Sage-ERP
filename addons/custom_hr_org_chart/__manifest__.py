{
    "name": "Custom HR Org Chart",
    "version": "19.0.1.0.0",
    "summary": "Custom HR org chart with multiple managers",
    "category": "Human Resources",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "hr_org_chart",
        "custom_hr_manager_multi_approver",
    ],
    "data": [
        "views/hr_employee_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "custom_hr_org_chart/static/src/fields/custom_hr_org_chart.js",
            "custom_hr_org_chart/static/src/fields/custom_hr_org_chart.xml",
            "custom_hr_org_chart/static/src/fields/custom_hr_org_chart.scss",
            "custom_hr_org_chart/static/src/views/hr_employee_hierarchy/custom_hr_employee_hierarchy_card.xml",
            "custom_hr_org_chart/static/src/views/hr_employee_hierarchy/custom_hr_employee_hierarchy_card.scss",
        ],
    },
    "installable": True,
    "application": False,
}