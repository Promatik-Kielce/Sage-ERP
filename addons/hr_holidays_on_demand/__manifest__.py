{
    'name': 'On-Demand Leave (Urlop na Żądanie)',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Time Off',
    'summary': 'Polish labor law: on-demand days from paid time off pool',
    'depends': ['hr_holidays'],
    'data': [
        'views/hr_leave_type_views.xml',
        'views/hr_leave_views.xml',
        'data/hr_leave_type_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hr_holidays_on_demand/static/src/dashboard/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
