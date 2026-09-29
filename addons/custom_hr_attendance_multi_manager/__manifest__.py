{
    "name": "HR Attendance Multi Manager",
    "version": "19.0.1.0.0",
    "summary": "All managers of an employee (not only the primary one) can see and manage their attendances",
    "category": "Human Resources/Attendances",
    "author": "Sage ERP",
    "license": "LGPL-3",
    "depends": [
        "hr_attendance",
        "custom_hr_manager_multi_approver",
    ],
    "data": [
        "security/hr_attendance_security.xml",
        "views/hr_attendance_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "auto_install": True,
    "application": False,
}
