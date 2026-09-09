# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models
from odoo.fields import Command

from .project_attachment_log import BIN_MODEL, TRACKED_MODELS

# Context keys, following the `project_task_no_description_log` precedent of
# `project.task`:
#   - `project_attachment_no_log`: this change is bookkeeping, do not audit it.
#   - `project_attachment_force_unlink`: really destroy the file instead of
#     soft deleting it (used when the whole task or project is deleted).
NO_LOG_CTX = 'project_attachment_no_log'
FORCE_UNLINK_CTX = 'project_attachment_force_unlink'

# Key under which the ids of freshly added attachments are aggregated, waiting
# for the precommit callback that decides whether they deserve a chatter note.
PRECOMMIT_KEY = 'project_attachment_history_added'


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _project_history_tracked(self):
        """ Subset of ``self`` holding user files on an audited record.

        Attachments with ``res_field`` set back a binary field rather than being
        a file of the record (base `_search` already hides them), so they are
        left alone.

        :return: a sudo recordset
        """
        if self.env.context.get(NO_LOG_CTX):
            return self.sudo().browse()
        # sudo: only reading the metadata needed to decide whether to audit.
        return self.sudo().filtered(
            lambda att: att.res_model in TRACKED_MODELS and att.res_id and not att.res_field
        )

    def _project_history_vals(self, action, **extra):
        """ Base audit values describing ``self`` at its current state. """
        self.ensure_one()
        vals = {
            'res_model': self.res_model,
            'res_id': self.res_id,
            'action': action,
            'attachment_id': self.id,
            'attachment_name': self.name,
            'file_size': self.file_size,
            'mimetype': self.mimetype,
            'checksum': self.checksum,
        }
        vals.update(extra)
        return vals

    def _project_history_message(self):
        """ The chatter message carrying this attachment, if any. """
        self.ensure_one()
        # sudo: same lookup as `/mail/attachment/delete`, needed to keep the
        # message and the file consistent.
        return self.env['mail.message'].sudo().search(
            [('attachment_ids', 'in', self.ids)], limit=1)

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        attachments = super().create(vals_list)
        tracked = attachments._project_history_tracked()
        if tracked:
            tracked._project_history_log_added()
        return attachments

    def write(self, vals):
        watched = self.env['ir.attachment']
        if self and not self.env.context.get(NO_LOG_CTX) and (
            {'res_model', 'res_id', 'name', 'raw', 'datas', 'db_datas'} & vals.keys()
        ):
            watched = self.sudo()
        before = {
            att.id: (att.res_model, att.res_id, att.name, att.checksum)
            for att in watched
        }
        # A content write destroys the previous bytes, so read them first: an old
        # snapshot has to be able to hand back the file as it was. Only done for
        # files actually under audit, and only when the content is being touched.
        previous_content = {}
        if before and {'raw', 'datas', 'db_datas'} & vals.keys():
            for att in watched._project_history_tracked():
                previous_content[att.id] = (att.name, att.mimetype, att.raw)
        res = super().write(vals)
        if before:
            watched.exists()._project_history_log_written(before, previous_content)
        return res

    def unlink(self):
        protected = self.browse()
        if not self.env.context.get(FORCE_UNLINK_CTX):
            protected = self._project_history_tracked()
        if protected:
            # The soft deleted files never reach `BaseModel.unlink`, so the
            # access check it would have run has to be done here instead.
            self.browse(protected.ids).check_access('unlink')
            protected._project_history_soft_delete()
        return super(IrAttachment, self - protected).unlink()

    # ------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------

    def _project_history_log_added(self):
        """ Record an ``added`` event, and schedule its chatter note. """
        logs = self.env['project.attachment.log']._log_events(
            [att._project_history_vals('added') for att in self])
        # The note is deferred to precommit: a file that ends up carried by a
        # chatter message is already documented by that message, and a second
        # note next to it would be noise. The audit row above is written in every
        # case, so the trail itself never has a hole.
        self.env.cr.precommit.data.setdefault(PRECOMMIT_KEY, set()).update(logs.ids)
        self.env.cr.precommit.add(self._project_history_notify_added)

    def _project_history_notify_added(self):
        log_ids = self.env.cr.precommit.data.pop(PRECOMMIT_KEY, None)
        if not log_ids:
            return
        logs = self.env['project.attachment.log'].sudo().browse(log_ids).exists()
        attachments = logs.attachment_id
        # Files a chatter message already accounts for, and files that left the
        # audited models again before the commit, need no note of their own.
        carried_ids = set()
        if attachments:
            carried_ids = set(self.env['mail.message'].sudo().search(
                [('attachment_ids', 'in', attachments.ids)]
            ).attachment_ids.ids)
        logs.filtered(
            lambda log: log.attachment_id
            and log.attachment_id.id not in carried_ids
            and log.attachment_id.res_model == log.res_model
            and log.attachment_id.res_id == log.res_id
        )._notify_record()

    def _record_label(self, res_model, res_id):
        """ Human readable label for a (res_model, res_id) couple, if any. """
        if not res_model or res_model not in self.env:
            return res_model or ''
        record = self.env[res_model].browse(res_id).sudo().exists()
        return record.display_name if record else res_model

    def _project_history_park_content(self, log, name, mimetype, raw):
        """ Keep the bytes a file had before it was overwritten.

        The copy is parked on the log row of the replacement, the same way a soft
        deleted file is parked on the row of its deletion, so an older snapshot
        can serve it.
        """
        copy = self.env['ir.attachment'].sudo().with_context(**{NO_LOG_CTX: True}).create({
            'name': name,
            'raw': raw,
            'mimetype': mimetype,
            'res_model': BIN_MODEL,
            'res_id': log.id,
        })
        log.sudo().write({'previous_attachment_id': copy.id})
        return copy

    def _project_history_log_written(self, before, previous_content=None):
        """ Turn a write into audit events.

        :param dict before: attachment id -> (res_model, res_id, name, checksum)
            as they were before the write.
        :param dict previous_content: attachment id -> (name, mimetype, raw) for
            the files whose content the write is about to replace.
        """
        previous_content = previous_content or {}
        Log = self.env['project.attachment.log']
        for att in self:
            old_model, old_id, old_name, old_checksum = before[att.id]
            was_tracked = old_model in TRACKED_MODELS and old_id
            is_tracked = att.res_model in TRACKED_MODELS and att.res_id and not att.res_field
            moved = (old_model, old_id) != (att.res_model, att.res_id)

            if moved and not was_tracked and is_tracked:
                # The pending-upload path: `_process_attachments_for_post` moves
                # the file from `mail.compose.message` onto the record, so this
                # is the point where a message attachment becomes a record file.
                att._project_history_log_added()
                continue

            if moved and was_tracked:
                old_label = self._record_label(old_model, old_id)
                new_label = self._record_label(att.res_model, att.res_id)
                # Directional: replaying a snapshot needs to know whether the file
                # left this record or arrived on it.
                events = [att._project_history_vals(
                    'moved_out',
                    res_model=old_model, res_id=old_id,
                    previous_name=new_label,
                )]
                if is_tracked:
                    # Audited on both sides, so that neither record loses track
                    # of the file.
                    events.append(att._project_history_vals(
                        'moved_in', previous_name=old_label))
                if is_tracked or att.res_model != BIN_MODEL:
                    Log._log_events(events)._notify_record()
                continue

            if not is_tracked:
                continue

            events = []
            if old_name != att.name:
                events.append(att._project_history_vals('renamed', previous_name=old_name))
            replaced = old_checksum != att.checksum
            if replaced:
                events.append(att._project_history_vals(
                    'replaced', previous_checksum=old_checksum))
            if not events:
                continue
            logs = Log._log_events(events)
            if replaced and att.id in previous_content:
                old_name_before, old_mimetype, old_raw = previous_content[att.id]
                replaced_log = logs.filtered(lambda log: log.action == 'replaced')
                att._project_history_park_content(
                    replaced_log, old_name_before, old_mimetype, old_raw)
            logs._notify_record()

    def _project_history_soft_delete(self):
        """ Park the files on their own audit row instead of destroying them.

        `ir.attachment` cannot carry an ``active`` field (base `_search` asserts
        it), so the file is re-pointed at the `project.attachment.log` record of
        the deletion. It stops matching `_get_mail_thread_data_attachments`, and
        therefore leaves the Files box, while the content is kept intact.
        """
        Log = self.env['project.attachment.log']
        for att in self:
            message = att._project_history_message()
            record = self.env[att.res_model].browse(att.res_id).sudo().exists()

            log = Log._log_events([att._project_history_vals(
                'deleted', message_id=message.id or False)])

            if message:
                # Detach from the message too, otherwise the file would stay
                # visible on it. `action_restore` puts the link back.
                message.write({'attachment_ids': [Command.unlink(att.id)]})
            if record and record._name in TRACKED_MODELS and \
                    getattr(record, 'message_main_attachment_id', False) == att:
                record.message_main_attachment_id = False

            att.with_context(**{NO_LOG_CTX: True}).write({
                'res_model': BIN_MODEL,
                'res_id': log.id,
            })
            log._notify_record()
