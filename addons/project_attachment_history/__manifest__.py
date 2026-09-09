# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Project Attachment History',
    'version': '19.0.1.1.0',
    'category': 'Services/Project',
    'summary': 'Audit trail and recycle bin for files attached to projects and tasks',
    'description': """
Project Attachment History
==========================

Projects and tasks are used to hold specifications, so their attachments must not
be silently swapped. This module makes every attachment change on
``project.project`` and ``project.task`` visible and reversible:

* Uploading, renaming, replacing, moving or deleting a file logs a note in the
  chatter of the record, naming the user and the file.
* Deleting a file is a *soft* delete. The attachment is parked on its own history
  record instead of being destroyed, so it disappears from the Files box but the
  content is preserved.
* A deleted file can be restored from the chatter note or from the
  ``Project / Configuration / Attachment History`` list.
* Every event is also stored in the ``project.attachment.log`` model, which nobody
  can edit or delete through the interface. Filename, size and checksum are kept
  denormalised, so the trail survives the deletion of the task itself.
""",
    'author': 'Sage-ERP',
    'license': 'LGPL-3',
    'depends': ['project', 'mail', 'html_editor'],
    'data': [
        'security/ir.model.access.csv',
        'security/project_attachment_history_security.xml',
        'views/project_attachment_log_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'project_attachment_history/static/src/scss/attachment_history_dialog.scss',
            'project_attachment_history/static/src/xml/attachment_history_dialog.xml',
            'project_attachment_history/static/src/js/attachment_history_dialog.js',
            'project_attachment_history/static/src/js/attachment_history_link_patch.js',
            'project_attachment_history/static/src/js/form_controller_patch.js',
        ],
    },
    'post_init_hook': '_backfill_attachment_history',
    'installable': True,
    'application': False,
}
