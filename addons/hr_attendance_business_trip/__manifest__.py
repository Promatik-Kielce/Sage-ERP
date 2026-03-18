{
    "name": "HR Attendance Business Trip",
    "version": "19.0.1.0.0",
    "author": "Sage ERP",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "hr_attendance",
        "mail",
        "project",
        "hr_attendance_timesheet_project",
    ],
    "data": [
        "security/hr_business_trip_security.xml",
        "security/ir.model.access.csv",
        "views/hr_business_trip_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_attendance_business_trip/static/src/scss/business_trip.scss",
            "hr_attendance_business_trip/static/src/js/attendance_gantt_patch.js",
        ],
    },
    "installable": True,
    "application": False,
}