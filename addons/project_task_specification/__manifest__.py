{
    "name": "Project Task Specification",
    "version": "19.0.1.0.0",
    "summary": "Project specification tiles and button in project task top bar",
    "category": "Project",
    "author": "Your Company",
    "license": "LGPL-3",
    "depends": ["project", "web", "mail"],
    "data": [
        "security/project_task_specification_groups.xml",
        "security/ir.model.access.csv",
        "views/project_task_specification_views.xml",
        "views/project_task_specification_actions.xml",
    ],
    "assets": {
    "web.assets_backend": [
        "project_task_specification/static/src/xml/project_task_spec_templates.xml",
        "project_task_specification/static/src/js/project_task_spec_button.js",
        "project_task_specification/static/src/scss/project_task_spec_button.scss",
    ],
    "web.assets_web": [
        "project_task_specification/static/src/xml/project_task_spec_templates.xml",
        "project_task_specification/static/src/js/project_task_spec_button.js",
        "project_task_specification/static/src/scss/project_task_spec_button.scss",
    ],
},
    "installable": True,
    "application": False,
}