# Part of Sage-ERP. See LICENSE file for full copyright and licensing details.

{
    'name': 'Web Gantt View',
    'version': '19.0.1.0.0',
    'category': 'Hidden',
    'summary': 'Gantt view for Odoo Community Edition',
    'description': """
Web Gantt View
==============
This module adds Gantt view support to Odoo Community Edition.

Features:
---------
* Timeline visualization with start/end dates
* Color coding support
* Grouping by any field
* Multiple time scales (day, week, month, year)
* Drag and drop to reschedule tasks
* Progress indicators
* Responsive design

Usage:
------
Define a gantt view in your model's views:

    <gantt
        date_start="date_start"
        date_stop="date_end"
        color="user_id"
        default_group_by="project_id"
        default_scale="month">
        <field name="name"/>
        <field name="user_id"/>
    </gantt>
    """,
    'author': 'Sage-ERP',
    'website': 'https://github.com/your-repo/sage-erp',
    'license': 'LGPL-3',
    'depends': ['web'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            # Third-party library - vis-timeline (Apache 2.0 license)
            'web_gantt/static/lib/vis-timeline/vis-timeline.min.css',
            'web_gantt/static/lib/vis-timeline/vis-timeline.min.js',

            # JavaScript files in dependency order
            'web_gantt/static/src/gantt_arch_parser.js',
            'web_gantt/static/src/gantt_model.js',
            'web_gantt/static/src/gantt_renderer.js',
            'web_gantt/static/src/gantt_controller.js',
            'web_gantt/static/src/gantt_view.js',  # Must be last - registers the view

            # Templates
            'web_gantt/static/src/gantt_renderer.xml',
            'web_gantt/static/src/gantt_controller.xml',

            # Styles
            'web_gantt/static/src/gantt_view.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
