{
    'name': 'Custom UI Tweaks',
    'version': '1.0',
    'depends': ['web'],
    'assets': {
        'web.assets_backend': [
            'custom_ui_tweaks/static/src/scss/ui_readability.scss',
        ],
    },
    'installable': True,
    'application': False,
}