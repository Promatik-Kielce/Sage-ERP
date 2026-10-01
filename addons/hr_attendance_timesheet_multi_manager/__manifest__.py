{
    "name": "Attendance Timesheets - Multi Manager",
    "version": "19.0.1.0.0",
    "summary": "Secondary managers can see and edit the timesheets linked to their team's attendances",
    "category": "Human Resources/Attendances",
    "author": "Sage ERP",
    "license": "LGPL-3",
    "depends": [
        "hr_attendance_timesheet_project",
        "custom_hr_attendance_multi_manager",
    ],
    "data": [
        "security/timesheet_security.xml",
    ],
    "installable": True,
    "auto_install": True,
    "application": False,
}
