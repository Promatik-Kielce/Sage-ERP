{
    "name": "HR Leave Multi Approver",
    "version": "19.0.1.0.0",
    "depends": ["hr", "hr_holidays", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/hr_employee_views.xml",
        "views/hr_leave_actions.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}