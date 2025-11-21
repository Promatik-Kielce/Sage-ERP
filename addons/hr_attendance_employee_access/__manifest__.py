{
    'name': 'HR Attendance Employee Access',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Allow all employees read-only access to all attendance records',
    'description': """
HR Attendance Employee Access
==============================

This module extends the hr_attendance module to provide read-only access
to all attendance records for all employees.

Features:
---------
* All employees can view all attendance records (full transparency)
* Read-only access - employees cannot create, edit, or delete records
* Accessible through list and gantt views
* Separate menu item for employee access

Purpose:
--------
Promotes workplace transparency by allowing all employees to see
attendance data while maintaining data integrity through read-only access.
    """,
    'author': 'Sage-ERP',
    'website': '',
    'depends': ['hr_attendance'],
    'data': [
        'security/hr_attendance_security.xml',
        'security/ir.model.access.csv',
        'views/hr_attendance_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
