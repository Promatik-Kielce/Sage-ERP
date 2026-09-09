# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import models

from .models.project_attachment_log import TRACKED_MODELS


def _backfill_attachment_history(env):
    """ Give the files that predate this module an ``added`` event.

    Without it they would look absent in every snapshot taken before their first
    later change. The date and author come from the attachment itself, so nothing
    is invented; files deleted before the install are simply gone.
    """
    attachments = env['ir.attachment'].sudo().search([
        ('res_model', 'in', list(TRACKED_MODELS)),
        ('res_id', '!=', False),
        ('res_field', '=', False),
    ], order='id asc')
    if not attachments:
        return
    already_logged = set(env['project.attachment.log'].sudo().search([
        ('action', '=', 'added'),
        ('attachment_id', 'in', attachments.ids),
    ]).attachment_id.ids)

    vals_list = []
    for attachment in attachments:
        if attachment.id in already_logged:
            continue
        record = env[attachment.res_model].browse(attachment.res_id).exists()
        if not record:
            continue
        vals_list.append({
            'res_model': attachment.res_model,
            'res_id': attachment.res_id,
            'action': 'added',
            'attachment_id': attachment.id,
            'attachment_name': attachment.name,
            'file_size': attachment.file_size,
            'mimetype': attachment.mimetype,
            'checksum': attachment.checksum,
            'user_id': attachment.create_uid.id or env.ref('base.user_root').id,
            'date': attachment.create_date,
        })
    if vals_list:
        # No chatter note: these events are being recorded now but happened long
        # ago, and back-dated notes in the chatter would be misleading.
        env['project.attachment.log']._log_events(vals_list)
