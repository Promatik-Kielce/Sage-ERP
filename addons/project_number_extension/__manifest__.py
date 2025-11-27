# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Project Number Extension',
    'version': '19.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Separate project numbers from names with unique validation',
    'description': """
        Project Number Extension
        =========================

        Adds a dedicated project_number field to projects:
        - Globally unique project numbers
        - Display as "number - name" throughout the system
        - Automatic migration for existing projects

        Features:
        ---------
        * Separate project_number field (required, globally unique)
        * Display format: "PROJECT_NUMBER - Project Name"
        * Automatic migration of existing projects
        * Search by number or name
        * Tracked changes in chatter
    """,
    'depends': ['project'],
    'data': [
        'data/project_sequence.xml',
        'security/ir.model.access.csv',
        'views/project_project_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
