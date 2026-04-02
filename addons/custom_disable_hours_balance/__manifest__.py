{
    "name": "Custom Disable Hours Balance",
    "version": "19.0.1.0.0",
    "summary": "Disable Hours Balance, Adjustments and Adjust Balance in hr_attendance",
    "category": "Human Resources",
    "depends": ["hr_attendance"],
    "data": [
        "views/xml/hide_hours_balance_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "custom_disable_hours_balance/static/src/xml/attendance_menu.xml",
            "custom_disable_hours_balance/static/src/scss/hide_hours_balance.scss",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
    "post_init_hook": "post_init_hook",
}