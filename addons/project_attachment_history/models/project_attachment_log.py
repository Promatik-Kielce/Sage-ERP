# Part of Odoo. See LICENSE file for full copyright and licensing details.

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tools import human_size

from odoo.addons.mail.tools.discuss import Store

# Models whose attachments are audited. Defined here rather than in
# `ir_attachment.py`, which imports them, so the modules stay acyclic.
TRACKED_MODELS = ('project.task', 'project.project')

# While an attachment is soft deleted it is parked on the log record that
# recorded the deletion, so it stops matching the thread attachment search.
BIN_MODEL = 'project.attachment.log'

# Actions that put a file on the record, and that take it off again, as replayed
# by `_replay_events`. Any other action only changes the file in place.
ADDING_ACTIONS = ('added', 'restored', 'moved_in')
REMOVING_ACTIONS = ('deleted', 'moved_out')

# `revision_id` sentinel meaning "the live state", as `HistoryDialog` uses it.
CURRENT_REVISION = -1


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
        ('moved_in', 'Moved here'),
        ('moved_out', 'Moved away'),
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

    # On a `replaced` event: a parked copy of the bytes as they were *before* the
    # write. Without it an old snapshot could only ever serve the current bytes.
    previous_attachment_id = fields.Many2one(
        'ir.attachment', string="Previous Content", ondelete='set null', readonly=True)

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
        note holding a `Markup` body, so that the links can be clickable. Every
        note carries a "View history" link opening the timeline dialog; a
        deletion also keeps a one-click "Restore".
        """
        self.ensure_one()
        name = self.attachment_name or ''
        size = human_size(self.file_size) or ''
        other = self.previous_name or ''
        labels = {
            'added': _("File added: %(name)s (%(size)s)", name=name, size=size),
            'deleted': _("File deleted: %(name)s (%(size)s)", name=name, size=size),
            'restored': _("File restored: %(name)s (%(size)s)", name=name, size=size),
            'renamed': _("File renamed: %(old)s → %(new)s", old=other, new=name),
            'replaced': _("File replaced: %(name)s (content changed)", name=name),
            'moved_in': _("File moved here from %(other)s: %(name)s", other=other, name=name),
            'moved_out': _("File moved to %(other)s: %(name)s", other=other, name=name),
        }
        label = labels.get(self.action)
        if not label:
            return Markup()
        body = Markup('%(label)s —') % {'label': label}
        if self.action == 'deleted':
            body += Markup(
                ' <a href="#" class="o_project_attachment_restore" '
                'data-oe-model="project.attachment.log" data-oe-id="%(log_id)s">%(link)s</a> ·'
            ) % {'log_id': self.id, 'link': _("Restore")}
        body += Markup(
            ' <a href="#" class="o_project_attachment_history" '
            'data-oe-model="%(res_model)s" data-oe-id="%(res_id)s">%(link)s</a>'
        ) % {
            'res_model': self.res_model,
            'res_id': self.res_id,
            'link': _("View history"),
        }
        return body

    # ------------------------------------------------------------
    # Point in time reconstruction
    # ------------------------------------------------------------

    @api.model
    def _check_history_access(self, res_model, res_id, operation='read'):
        """ Guard for the public methods below.

        They are `@api.model` and therefore reachable by any logged in user with
        arbitrary arguments, so the record they are asked about has to be checked
        explicitly.
        """
        if res_model not in TRACKED_MODELS:
            raise UserError(_("Attachment history is not tracked for this model."))
        record = self.env[res_model].browse(int(res_id)).exists()
        if not record:
            raise UserError(_("This record no longer exists."))
        record.check_access(operation)
        return record

    def _event_summary(self):
        """ One short line describing this event, for the timeline rail. """
        self.ensure_one()
        name = self.attachment_name or ''
        other = self.previous_name or ''
        return {
            'added': _("Added %(name)s", name=name),
            'deleted': _("Deleted %(name)s", name=name),
            'restored': _("Restored %(name)s", name=name),
            'renamed': _("Renamed %(old)s to %(new)s", old=other, new=name),
            'replaced': _("Replaced the content of %(name)s", name=name),
            'moved_in': _("Moved %(name)s here from %(other)s", name=name, other=other),
            'moved_out': _("Moved %(name)s to %(other)s", name=name, other=other),
        }.get(self.action, self.action or '')

    @api.model
    def _history_events(self, res_model, res_id):
        """ Every event of a record, oldest first, as sudo.

        Access is the caller's responsibility (`_check_history_access`): the rows
        are read in sudo so that the replay is complete even when a single file
        happens to sit outside the reader's reach.
        """
        return self.sudo().search(
            [('res_model', '=', res_model), ('res_id', '=', res_id)], order='id asc')

    @api.model
    def _replay_events(self, events):
        """ Replay an event stream into the set of files present at its end.

        :param events: `project.attachment.log` records, oldest first
        :return: dict attachment id -> {'name', 'log'} as of the last event
        """
        present = {}
        for event in events:
            attachment_id = event.attachment_id.id
            if not attachment_id:
                # The file was destroyed for real (the whole task was deleted).
                # The row still documents what happened, but there is nothing to
                # put in a snapshot.
                continue
            if event.action in ADDING_ACTIONS:
                present[attachment_id] = {'name': event.attachment_name, 'log': event}
            elif event.action in REMOVING_ACTIONS:
                present.pop(attachment_id, None)
            elif attachment_id in present:
                # `renamed` / `replaced`: the file stays, its metadata moves on.
                present[attachment_id] = {'name': event.attachment_name, 'log': event}
        return present

    @api.model
    def _content_at_revision(self, attachment, events_after):
        """ The attachment holding the bytes a file had at a past revision.

        Walking forward from that revision, the first `replaced` event carries in
        `previous_attachment_id` exactly the bytes that were current before it —
        that is, the bytes at the revision we are looking at. With no later
        replacement the live attachment still holds them (or the parked original,
        if the file was deleted since).
        """
        for event in events_after:
            if (event.action == 'replaced'
                    and event.attachment_id.id == attachment.id
                    and event.previous_attachment_id):
                return event.previous_attachment_id
        return attachment

    @api.model
    def get_attachment_history(self, res_model, res_id):
        """ The timeline rail of a record.

        :return: {'revisions': [...newest first...], 'record': {...}}
        """
        record = self._check_history_access(res_model, res_id)
        events = self._history_events(res_model, res_id)
        revisions = [{
            'revision_id': event.id,
            'create_date': event.date.isoformat(),
            'create_uid': event.user_id.id,
            'create_user_name': event.user_id.display_name,
            'action': event.action,
            'attachment_name': event.attachment_name,
            'summary': event._event_summary(),
        } for event in reversed(events)]
        record_sudo = record.sudo()
        return {
            'revisions': revisions,
            'record': {
                'display_name': record_sudo.display_name,
                'create_date': record_sudo.create_date and record_sudo.create_date.isoformat(),
                'create_uid': record_sudo.create_uid.id,
                'create_user_name': record_sudo.create_uid.display_name,
            },
        }

    @api.model
    def get_attachment_snapshot(self, res_model, res_id, revision_id):
        """ The files present on a record just after `revision_id`.

        `revision_id` is a `project.attachment.log` id, or `CURRENT_REVISION` for
        the live state.

        :return: {'files': [...], 'summary': str}
        """
        record = self._check_history_access(res_model, res_id)
        revision_id = int(revision_id)
        events = self._history_events(res_model, res_id)

        if revision_id == CURRENT_REVISION:
            # Read the live set rather than replaying, so that anything that ever
            # slipped past the audit still shows up in "Current".
            attachments = record.sudo()._get_mail_thread_data_attachments()
            present = {att.id: {'name': att.name, 'log': self.browse()} for att in attachments}
            events_after = self.browse()
            changed_ids = set()
        else:
            up_to = events.filtered(lambda e: e.id <= revision_id)
            present = self._replay_events(up_to)
            events_after = events.filtered(lambda e: e.id > revision_id)
            selected = events.filtered(lambda e: e.id == revision_id)
            changed_ids = set(selected.attachment_id.ids)

        live_ids = set(record.sudo()._get_mail_thread_data_attachments().ids)
        attachments = self.env['ir.attachment'].sudo().browse(present.keys()).exists()

        # sudo: the caller passed `check_access('read')` on the record above, so
        # they are entitled to its files; the parked ones live on a bin record
        # they may not reach directly.
        store = Store()
        files = []
        for attachment in attachments:
            content = self._content_at_revision(attachment, events_after)
            store.add(content)
            entry = present[attachment.id]
            selected_event = entry['log']
            files.append({
                'attachment_id': content.id,
                'name': entry['name'] or content.name,
                'present_now': attachment.id in live_ids,
                'changed_here': attachment.id in changed_ids and selected_event.action or False,
                'log_id': selected_event.id or False,
                'is_historical_content': content.id != attachment.id,
                'restore_log_id': self._restorable_log_id(attachment),
            })
        return {
            'files': files,
            'store_data': store.get_result(),
            'summary': self._revision_summary(events, revision_id),
        }

    @api.model
    def _restorable_log_id(self, attachment):
        """ The log row a currently parked file can be restored from, if any. """
        if attachment.sudo().res_model != BIN_MODEL:
            return False
        log = self.sudo().browse(attachment.sudo().res_id).exists()
        return log.id if log and log.action == 'deleted' else False

    @api.model
    def _revision_summary(self, events, revision_id):
        if revision_id == CURRENT_REVISION:
            return _("Current files")
        event = events.filtered(lambda e: e.id == revision_id)
        return event._event_summary() if event else ''

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

    @api.model
    def action_restore_snapshot(self, res_model, res_id, revision_id):
        """ Bring the whole attachment set back to how it was at a revision.

        Files that were present then and are missing now are restored; files that
        are present now and were not there then are soft deleted. Both directions
        go through the ordinary paths, so the bulk change is itself audited and
        just as reversible as any other.
        """
        record = self._check_history_access(res_model, res_id, operation='write')
        revision_id = int(revision_id)
        if revision_id == CURRENT_REVISION:
            return False

        events = self._history_events(res_model, res_id)
        wanted_ids = set(self._replay_events(events.filtered(lambda e: e.id <= revision_id)))
        live = record.sudo()._get_mail_thread_data_attachments()
        live_ids = set(live.ids)

        for attachment_id in sorted(wanted_ids - live_ids):
            attachment = self.env['ir.attachment'].sudo().browse(attachment_id).exists()
            log = self.sudo().browse(self._restorable_log_id(attachment)) if attachment else None
            if log:
                log.action_restore()

        to_remove = live.filtered(lambda att: att.id not in wanted_ids)
        if to_remove:
            # The ordinary delete path: soft delete, chatter note and audit row.
            # sudo: reverting the set is a change of the record, and write access
            # on it was checked above; the individual files are reached through
            # it, exactly as the Files box reaches them.
            to_remove.unlink()
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
