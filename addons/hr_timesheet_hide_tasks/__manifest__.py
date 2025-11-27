# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Hide Task Timesheets',
    'version': '1.0.0',
    'category': 'Human Resources/Timesheets',
    'summary': 'Hide task-based timesheet UI (attendance-based workflow)',
    'description': """
Hide Task-Based Timesheet UI Elements
======================================

This module hides all task-based timesheet UI elements while preserving the
attendance-based timesheet workflow provided by hr_attendance_timesheet_project.

What it does:
-------------
* Hides "Timesheets" tab in task forms
* Hides timesheet-related columns in task lists
* Hides timesheet progress badges in kanban view
* Hides task_id field in timesheet forms/lists
* Hides "By Task" reporting menu
* Restricts timesheet field visibility to technical users

Why use this:
-------------
* Your organization uses attendance-based timesheets exclusively
* Task-based timesheet UI creates confusion for users
* You want a cleaner, simpler task interface

Technical approach:
-------------------
* Uses view inheritance to hide UI elements (zero core code changes)
* Restricts field visibility via groups (base.group_no_one)
* Fully reversible by uninstalling the module
* All data preserved, no deletions

Compatibility:
--------------
* Requires: hr_timesheet, hr_attendance_timesheet_project
* Optional: sale_timesheet (if installed, you may want additional customization)
* Odoo version: 19.0
    """,
    'depends': [
        'hr_timesheet',
        'hr_attendance_timesheet_project',
    ],
    'data': [
        'views/project_task_views.xml',
        'views/hr_timesheet_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
