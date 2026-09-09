# Part of Odoo. See LICENSE file for full copyright and licensing details.

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tools import human_size

# Models whose attachments are audited. Defined here rather than in
# `ir_attachment.py`, which imports them, so the modules stay acyclic.
TRACKED_MODELS = ('project.task', 'project.project')

# While an attachment is soft deleted it is parked on the log record that
# recorded the deletion, so it stops matching the thread attachment search.
BIN_MODEL = 'project.attachment.log'


class ProjectAttachmentLog(models.Model):
    _name = 'project.attachment.log'
    _description = 'Project Attachment History'
    _order = 'id desc'
    _rec_name = 'attachment_name'

    # The audited record. `res_name` is denormalised on purpose: it must survive
    # the deletion of the task or project itself.
    res_model = fields.Char(string="Model", required=True, index=True, readonly=True)
    res_id = fields.Many2oneReference(
        string="Record ID", model_field='res_model', required=True, index=True, readonly=True)
    res_name = fields.Char(string="Record", readonly=True)
    task_id = fields.Many2one(
        'project.task', string="Task", ondelete='set null', index='btree_not_null', readonly=True)
    project_id = fields.Many2one(
        'project.project', string="Project", ondelete='set null', index='btree_not_null', readonly=True)

    action = fields.Selection([
        ('added', 'Added'),
        ('deleted', 'Deleted'),
        ('restored', 'Restored'),
        ('renamed', 'Renamed'),
        ('replaced', 'Content replaced'),
        ('moved', 'Moved'),
    ], string="Action", required=True, index=True, readonly=True)

    # `attachment_id` also owns the file while it is soft deleted. It is emptied
    # when the file is really destroyed (deletion of the whole task for instance),
    # which is why the file metadata below is denormalised as well.
    attachment_id = fields.Many2one(
        'ir.attachment', string="Attachment", ondelete='set null', readonly=True)
    attachment_name = fields.Char(string="File", required=True, readonly=True)
    previous_name = fields.Char(string="Previous Value", readonly=True)
    file_size = fields.Integer(string="Size (bytes)", readonly=True)
    file_size_human = fields.Char(
        string="Size", compute='_compute_file_size_human', export_string_translation=False)
    mimetype = fields.Char(string="Type", readonly=True)
    checksum = fields.Char(string="Checksum", readonly=True)
    previous_checksum = fields.Char(string="Previous Checksum", readonly=True)

    # Set when the file was carried by a chatter message, so that a restore can
    # put it back on that message.
    message_id = fields.Many2one('mail.message', string="Message", ondelete='set null', readonly=True)

    user_id = fields.Many2one(
        'res.users', string="User", required=True, readonly=True,
        default=lambda self: self.env.user, index='btree_not_null')
    date = fields.Datetime(string="Date", required=True, readonly=True, default=fields.Datetime.now)

    is_recoverable = fields.Boolean(
        string="Recoverable", compute='_compute_is_recoverable', search='_search_is_recoverable')

    @api.depends('file_size')
    def _compute_file_size_human(self):
        for log in self:
            log.file_size_human = human_size(log.file_size) or ''

    # The file leaving or entering the bin is a change of the attachment's own
    # `res_model`/`res_id`, not of the log row, hence the dotted dependencies.
    @api.depends('action', 'attachment_id.res_model', 'attachment_id.res_id')
    def _compute_is_recoverable(self):
        # sudo: the parked attachment is readable through this log record anyway,
        # but computing the flag must not depend on the reader's rights.
        bin_ids = set(self.sudo().filtered(
            lambda log: log.attachment_id
            and log.attachment_id.res_model == BIN_MODEL
            and log.attachment_id.res_id == log.id
        ).ids)
        for log in self:
            log.is_recoverable = log.action == 'deleted' and log.id in bin_ids

    def _search_is_recoverable(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        # A log row is recoverable when the file is parked on it. One query on
        # the bin answers that for every row at once.
        # sudo: resolving the search only, the result is still filtered by the
        # record rules of `project.attachment.log`.
        parked = self.env['ir.attachment'].sudo().search_fetch(
            [('res_model', '=', BIN_MODEL)], ['res_id'])
        domain = Domain('action', '=', 'deleted') & Domain('id', 'in', parked.mapped('res_id'))
        positive = (operator == 'in') == (True in value)
        return domain if positive else ~domain

    def unlink(self):
        # The audit trail is not meant to be erased. `sudo()` is still allowed so
        # that deleting a whole database or an uninstall keeps working.
        if not self.env.su:
            raise UserError(_("The attachment history cannot be deleted."))
        return super().unlink()

    # ------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------

    @api.model
    def _log_events(self, vals_list):
        """ Create audit rows. Always called from code, never from the interface.

        :param list vals_list: values, each holding at least ``res_model``,
            ``res_id``, ``action`` and ``attachment_name``.
        :return: the created records, as sudo
        """
        for vals in vals_list:
            vals.setdefault('user_id', self.env.uid)
            vals.setdefault('date', fields.Datetime.now())
            record = self.env[vals['res_model']].browse(vals['res_id']).sudo().exists()
            vals.setdefault('res_name', record.display_name if record else False)
            if vals['res_model'] == 'project.task':
                vals.setdefault('task_id', record.id or False)
                vals.setdefault('project_id', record.project_id.id or False)
            elif vals['res_model'] == 'project.project':
                vals.setdefault('project_id', record.id or False)
        # sudo: nobody has create rights on this model, rows are written by the
        # framework on behalf of the acting user, whose id is stored in `user_id`.
        return self.sudo().create(vals_list)

    def _notify_record(self):
        """ Post the chatter note describing this event on the audited record. """
        for log in self:
            record = self.env[log.res_model].browse(log.res_id).sudo().exists()
            if not record or not hasattr(record, '_message_log'):
                continue
            body = log._get_note_body()
            if body:
                record._message_log(body=body)

    def _get_note_body(self):
        """ Build the chatter note body for this event.

        Mirrors `project.task._log_description_update`: a plain `_message_log`
        note holding a `Markup` body, so that the restore link can be clickable.
        """
        self.ensure_one()
        name = self.attachment_name or ''
        size = human_size(self.file_size) or ''
        if self.action == 'added':
            return Markup('%(label)s') % {
                'label': _("File added: %(name)s (%(size)s)", name=name, size=size),
            }
        if self.action == 'deleted':
            return Markup(
                '%(label)s <a href="#" class="o_project_attachment_restore" '
                'data-oe-model="project.attachment.log" data-oe-id="%(log_id)s">%(link)s</a>'
            ) % {
                'label': _("File deleted: %(name)s (%(size)s) —", name=name, size=size),
                'log_id': self.id,
                'link': _("Restore"),
            }
        if self.action == 'restored':
            return Markup('%(label)s') % {
                'label': _("File restored: %(name)s (%(size)s)", name=name, size=size),
            }
        if self.action == 'renamed':
            return Markup('%(label)s') % {
                'label': _("File renamed: %(old)s → %(new)s", old=self.previous_name or '', new=name),
            }
        if self.action == 'replaced':
            return Markup('%(label)s') % {
                'label': _("File replaced: %(name)s (content changed)", name=name),
            }
        if self.action == 'moved':
            return Markup('%(label)s') % {
                'label': _("File moved: %(name)s (%(other)s)", name=name, other=self.previous_name or ''),
            }
        return Markup()

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def action_restore(self):
        """ Put a soft deleted file back on the record it was deleted from. """
        for log in self:
            if not log.is_recoverable:
                raise UserError(_("This file cannot be restored."))
            record = self.env[log.res_model].browse(log.res_id).exists()
            if not record:
                raise UserError(_(
                    "The record this file belonged to no longer exists, so it cannot be restored."))
            # Restoring is a change of the record: require the same rights as any
            # other edit of it, so this is not a way around the record's ACLs.
            record.check_access('write')

            attachment = log.attachment_id.sudo()
            attachment.with_context(project_attachment_no_log=True).write({
                'res_model': log.res_model,
                'res_id': log.res_id,
            })
            if log.message_id:
                # sudo: re-linking the file to the message it was posted with.
                log.message_id.sudo().write({'attachment_ids': [Command.link(attachment.id)]})
            attachment.register_as_main_attachment(force=False)

            restored = self._log_events([{
                'res_model': log.res_model,
                'res_id': log.res_id,
                'action': 'restored',
                'attachment_id': attachment.id,
                'attachment_name': attachment.name,
                'file_size': attachment.file_size,
                'mimetype': attachment.mimetype,
                'checksum': attachment.checksum,
                'message_id': log.message_id.id or False,
            }])
            restored._notify_record()
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    def action_open_record(self):
        self.ensure_one()
        record = self.env[self.res_model].browse(self.res_id).exists()
        if not record:
            raise UserError(_("This record no longer exists."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
