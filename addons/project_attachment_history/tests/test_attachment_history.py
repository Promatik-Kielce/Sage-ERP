# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged, users


@tagged('post_install', '-at_install', 'project_attachment_history')
class TestProjectAttachmentHistory(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_manager = cls.env['res.users'].create({
            'name': 'Attachment Manager',
            'login': 'attachment_manager',
            'email': 'attachment_manager@example.com',
            'group_ids': [Command.set([
                cls.env.ref('base.group_user').id,
                cls.env.ref('project.group_project_manager').id,
            ])],
        })
        cls.user_outsider = cls.env['res.users'].create({
            'name': 'Attachment Outsider',
            'login': 'attachment_outsider',
            'email': 'attachment_outsider@example.com',
            'group_ids': [Command.set([cls.env.ref('base.group_user').id])],
        })
        cls.project = cls.env['project.project'].create({'name': 'Spec Project'})
        cls.task = cls.env['project.task'].create({
            'name': 'Spec Task',
            'project_id': cls.project.id,
        })
        cls.Log = cls.env['project.attachment.log']

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _upload(self, record=None, name='spec_v1.pdf', raw=b'first version'):
        """ Create an attachment the way `/mail/attachment/upload` does. """
        record = record or self.task
        return self.env['ir.attachment'].create({
            'name': name,
            'raw': raw,
            'res_model': record._name,
            'res_id': record.id,
        })

    def _logs(self, attachment=None, action=None):
        domain = []
        if attachment:
            domain.append(('attachment_id', '=', attachment.id))
        if action:
            domain.append(('action', '=', action))
        return self.Log.search(domain)

    def _thread_attachments(self, record=None):
        record = record or self.task
        return record._get_mail_thread_data_attachments()

    # ------------------------------------------------------------
    # Add
    # ------------------------------------------------------------

    def test_upload_logs_added(self):
        messages_before = len(self.task.message_ids)
        attachment = self._upload()
        self.env.cr.precommit.run()

        log = self._logs(attachment, 'added')
        self.assertEqual(len(log), 1, "the upload must be recorded once")
        self.assertEqual(log.res_model, 'project.task')
        self.assertEqual(log.res_id, self.task.id)
        self.assertEqual(log.task_id, self.task)
        self.assertEqual(log.project_id, self.project)
        self.assertEqual(log.attachment_name, 'spec_v1.pdf')
        self.assertEqual(log.file_size, len(b'first version'))
        self.assertEqual(log.checksum, attachment.checksum)
        self.assertEqual(log.user_id, self.env.user)
        self.assertGreater(len(self.task.message_ids), messages_before,
                           "a chatter note must be logged for the upload")
        self.assertIn('spec_v1.pdf', self.task.message_ids[0].body)

    def test_upload_on_project_logs_added(self):
        attachment = self._upload(record=self.project, name='charter.pdf')
        self.env.cr.precommit.run()

        log = self._logs(attachment, 'added')
        self.assertEqual(len(log), 1)
        self.assertEqual(log.res_model, 'project.project')
        self.assertEqual(log.project_id, self.project)
        self.assertFalse(log.task_id)

    def test_message_attachment_logged_without_duplicate_note(self):
        """ A file posted with a message is audited, but the message itself is
        the chatter trace: no extra note is added next to it. """
        message = self.task.message_post(
            body='here is the spec',
            attachments=[('spec_v1.pdf', b'first version')],
        )
        self.env.cr.precommit.run()
        attachment = message.attachment_ids
        self.assertEqual(len(attachment), 1)

        self.assertEqual(len(self._logs(attachment, 'added')), 1,
                         "the audit row must exist even without a note")
        notes = self.task.message_ids.filtered(
            lambda m: m != message and 'spec_v1.pdf' in (m.body or ''))
        self.assertFalse(notes, "the message already documents the file")

    def test_pending_upload_moved_onto_record_logs_added(self):
        """ The composer uploads to `mail.compose.message` first; the file only
        becomes a record file when `_process_attachments_for_post` moves it. """
        attachment = self.env['ir.attachment'].create({
            'name': 'pending.pdf',
            'raw': b'pending',
            'res_model': 'mail.compose.message',
            'res_id': 0,
        })
        self.assertFalse(self._logs(attachment))

        attachment.write({'res_model': 'project.task', 'res_id': self.task.id})
        self.env.cr.precommit.run()
        self.assertEqual(len(self._logs(attachment, 'added')), 1)

    def test_binary_field_attachment_is_ignored(self):
        """ Attachments backing a binary field are not files of the record. """
        attachment = self.env['ir.attachment'].create({
            'name': 'avatar',
            'raw': b'binary field content',
            'res_model': 'project.task',
            'res_id': self.task.id,
            'res_field': 'attached_binary_field',
        })
        self.env.cr.precommit.run()
        self.assertFalse(self._logs(attachment))

    def test_unrelated_model_is_ignored(self):
        partner = self.env['res.partner'].create({'name': 'Somebody'})
        attachment = self._upload(record=partner, name='other.pdf')
        self.env.cr.precommit.run()
        self.assertFalse(self._logs(attachment))

    # ------------------------------------------------------------
    # Delete / restore
    # ------------------------------------------------------------

    def test_delete_is_soft_and_logged(self):
        attachment = self._upload()
        self.env.cr.precommit.run()
        self.assertIn(attachment, self._thread_attachments())

        # The exact path taken by `/mail/attachment/delete`.
        attachment._delete_and_notify()

        self.assertTrue(attachment.exists(), "the file must not be destroyed")
        self.assertEqual(attachment.raw, b'first version', "the content must be kept")
        self.assertNotIn(attachment, self._thread_attachments(),
                         "the file must leave the Files box")

        log = self._logs(attachment, 'deleted')
        self.assertEqual(len(log), 1)
        self.assertEqual(log.res_id, self.task.id)
        self.assertEqual(log.attachment_name, 'spec_v1.pdf')
        self.assertTrue(log.is_recoverable)
        self.assertEqual(attachment.res_model, 'project.attachment.log')
        self.assertEqual(attachment.res_id, log.id)
        self.assertIn('spec_v1.pdf', self.task.message_ids[0].body)
        self.assertIn('o_project_attachment_restore', self.task.message_ids[0].body)

    def test_restore_puts_the_file_back(self):
        attachment = self._upload()
        self.env.cr.precommit.run()
        attachment._delete_and_notify()
        log = self._logs(attachment, 'deleted')

        log.action_restore()

        self.assertEqual(attachment.res_model, 'project.task')
        self.assertEqual(attachment.res_id, self.task.id)
        self.assertIn(attachment, self._thread_attachments())
        self.assertEqual(attachment.raw, b'first version')
        self.assertEqual(len(self._logs(attachment, 'restored')), 1)
        self.assertFalse(log.is_recoverable, "the file is no longer in the bin")

    def test_restore_relinks_the_message(self):
        message = self.task.message_post(
            body='here is the spec',
            attachments=[('spec_v1.pdf', b'first version')],
        )
        self.env.cr.precommit.run()
        attachment = message.attachment_ids

        attachment._delete_and_notify(message)
        self.assertNotIn(attachment, message.attachment_ids,
                         "the file must leave the message it was posted with")
        log = self._logs(attachment, 'deleted')
        self.assertEqual(log.message_id, message)

        log.action_restore()
        self.assertIn(attachment, message.attachment_ids)

    def test_restore_requires_write_access_on_the_record(self):
        attachment = self._upload()
        self.env.cr.precommit.run()
        attachment._delete_and_notify()
        log = self._logs(attachment, 'deleted')

        with self.assertRaises(AccessError):
            log.with_user(self.user_outsider).action_restore()

        # Somebody who may edit the task may bring the file back.
        log.with_user(self.user_manager).action_restore()
        self.assertIn(attachment, self._thread_attachments())

    def test_history_cannot_be_deleted(self):
        attachment = self._upload()
        self.env.cr.precommit.run()
        log = self._logs(attachment, 'added')
        with self.assertRaises(UserError):
            log.with_user(self.user_manager).unlink()

    # ------------------------------------------------------------
    # Rename / replace / move
    # ------------------------------------------------------------

    def test_rename_is_logged(self):
        attachment = self._upload()
        self.env.cr.precommit.run()

        attachment.write({'name': 'spec_v2.pdf'})

        log = self._logs(attachment, 'renamed')
        self.assertEqual(len(log), 1)
        self.assertEqual(log.previous_name, 'spec_v1.pdf')
        self.assertEqual(log.attachment_name, 'spec_v2.pdf')

    def test_content_replacement_is_logged(self):
        attachment = self._upload()
        self.env.cr.precommit.run()
        old_checksum = attachment.checksum

        attachment.write({'raw': b'second version'})

        log = self._logs(attachment, 'replaced')
        self.assertEqual(len(log), 1)
        self.assertEqual(log.previous_checksum, old_checksum)
        self.assertEqual(log.checksum, attachment.checksum)
        self.assertNotEqual(log.checksum, old_checksum)

    def test_move_to_another_task_is_logged_on_both_records(self):
        other_task = self.env['project.task'].create({
            'name': 'Other Task',
            'project_id': self.project.id,
        })
        attachment = self._upload()
        self.env.cr.precommit.run()

        attachment.write({'res_id': other_task.id})

        out = self._logs(attachment, 'moved_out')
        into = self._logs(attachment, 'moved_in')
        self.assertEqual(out.res_id, self.task.id, "the source records a departure")
        self.assertEqual(into.res_id, other_task.id, "the target records an arrival")

    def test_move_out_of_scope_is_logged(self):
        partner = self.env['res.partner'].create({'name': 'Somebody'})
        attachment = self._upload()
        self.env.cr.precommit.run()

        attachment.write({'res_model': 'res.partner', 'res_id': partner.id})

        logs = self._logs(attachment, 'moved_out')
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.res_model, 'project.task')
        self.assertEqual(logs.res_id, self.task.id)

    def test_detaching_the_file_entirely_is_logged(self):
        """ Emptying `res_model` must be audited, not crash. """
        attachment = self._upload()
        self.env.cr.precommit.run()

        attachment.write({'res_model': False, 'res_id': 0})

        logs = self._logs(attachment, 'moved_out')
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.res_id, self.task.id)

    def test_recoverable_filter(self):
        kept = self._upload(name='kept.pdf')
        removed = self._upload(name='removed.pdf', raw=b'to be removed')
        self.env.cr.precommit.run()
        removed._delete_and_notify()

        recoverable = self.Log.search([('is_recoverable', '=', True)])
        self.assertEqual(recoverable.attachment_id, removed)
        not_recoverable = self.Log.search([('is_recoverable', '=', False)])
        self.assertIn(kept, not_recoverable.attachment_id)
        self.assertNotIn(removed.id, not_recoverable.filtered(
            lambda log: log.action == 'deleted').attachment_id.ids)

    def test_soft_delete_still_checks_the_unlink_right(self):
        """ The files never reach `BaseModel.unlink`, so its access check must
        be done by the override instead. """
        attachment = self._upload()
        self.env.cr.precommit.run()

        with self.assertRaises(AccessError):
            attachment.with_user(self.user_outsider).unlink()
        self.assertFalse(self._logs(attachment, 'deleted'),
                         "a refused deletion must not be audited either")
        self.assertIn(attachment, self._thread_attachments())

    def test_delete_then_reupload_shows_two_checksums(self):
        """ The scenario the audit exists for: swap the specification. """
        first = self._upload(name='spec.pdf', raw=b'the agreed specification')
        self.env.cr.precommit.run()
        first._delete_and_notify()
        second = self._upload(name='spec.pdf', raw=b'a quietly different specification')
        self.env.cr.precommit.run()

        history = self.Log.search([('task_id', '=', self.task.id)], order='id asc')
        self.assertEqual(history.mapped('action'), ['added', 'deleted', 'added'])
        self.assertNotEqual(first.checksum, second.checksum)
        self.assertEqual(
            history.mapped('checksum'),
            [first.checksum, first.checksum, second.checksum],
            "the checksums make the swap visible")

    # ------------------------------------------------------------
    # Deletion of the record itself
    # ------------------------------------------------------------

    def test_task_deletion_really_removes_the_files_but_keeps_the_trail(self):
        attachment = self._upload()
        self.env.cr.precommit.run()
        attachment_id = attachment.id

        self.task.unlink()

        self.assertFalse(self.env['ir.attachment'].browse(attachment_id).exists(),
                         "the file must not be parked on a record that is gone")
        log = self.Log.search([('attachment_name', '=', 'spec_v1.pdf')])
        self.assertTrue(log, "the audit trail must survive the task")
        self.assertFalse(log.task_id)
        self.assertFalse(log.attachment_id)
        self.assertIn('Spec Task', log.res_name)
        self.assertTrue(log.checksum)

    # ------------------------------------------------------------
    # Point in time reconstruction
    # ------------------------------------------------------------

    def _snapshot_names(self, revision_id, record=None):
        record = record or self.task
        snapshot = self.Log.get_attachment_snapshot(record._name, record.id, revision_id)
        return sorted(f['name'] for f in snapshot['files'])

    def test_snapshot_replays_the_event_stream(self):
        a = self._upload(name='a.pdf', raw=b'aaa')
        self.env.cr.precommit.run()
        rev_a = self._logs(a, 'added').id

        b = self._upload(name='b.pdf', raw=b'bbb')
        self.env.cr.precommit.run()
        rev_b = self._logs(b, 'added').id

        a._delete_and_notify()
        rev_del = self._logs(a, 'deleted').id

        c = self._upload(name='c.pdf', raw=b'ccc')
        self.env.cr.precommit.run()
        rev_c = self._logs(c, 'added').id

        self.assertEqual(self._snapshot_names(rev_a), ['a.pdf'])
        self.assertEqual(self._snapshot_names(rev_b), ['a.pdf', 'b.pdf'])
        self.assertEqual(self._snapshot_names(rev_del), ['b.pdf'])
        self.assertEqual(self._snapshot_names(rev_c), ['b.pdf', 'c.pdf'])
        self.assertEqual(self._snapshot_names(-1), ['b.pdf', 'c.pdf'], "-1 is the live set")

    def test_snapshot_marks_what_is_gone_and_what_changed(self):
        attachment = self._upload()
        self.env.cr.precommit.run()
        attachment._delete_and_notify()
        rev_del = self._logs(attachment, 'deleted').id

        snapshot = self.Log.get_attachment_snapshot('project.task', self.task.id, rev_del)
        self.assertFalse(snapshot['files'], "the file is gone as of that event")

        rev_add = self._logs(attachment, 'added').id
        snapshot = self.Log.get_attachment_snapshot('project.task', self.task.id, rev_add)
        entry = snapshot['files'][0]
        self.assertEqual(entry['changed_here'], 'added')
        self.assertFalse(entry['present_now'], "it has been deleted since")
        self.assertTrue(entry['restore_log_id'], "and it can be brought back")

    def test_snapshot_replays_moves_on_both_records(self):
        other_task = self.env['project.task'].create({
            'name': 'Other Task', 'project_id': self.project.id,
        })
        attachment = self._upload(name='travelling.pdf')
        self.env.cr.precommit.run()
        attachment.write({'res_id': other_task.id})

        out = self._logs(attachment, 'moved_out')
        into = self._logs(attachment, 'moved_in')
        self.assertEqual(self._snapshot_names(out.id), [], "gone from the source")
        self.assertEqual(
            self._snapshot_names(into.id, record=other_task), ['travelling.pdf'],
            "present on the target")

    def test_snapshot_serves_the_content_of_that_time(self):
        attachment = self._upload(name='spec.pdf', raw=b'version one')
        self.env.cr.precommit.run()
        rev_before = self._logs(attachment, 'added').id

        attachment.write({'raw': b'version two'})
        rev_after = self._logs(attachment, 'replaced').id

        snapshot = self.Log.get_attachment_snapshot('project.task', self.task.id, rev_before)
        entry = snapshot['files'][0]
        self.assertTrue(entry['is_historical_content'])
        old = self.env['ir.attachment'].sudo().browse(entry['attachment_id'])
        self.assertNotEqual(old, attachment, "a parked copy holds the old bytes")
        self.assertEqual(old.raw, b'version one')

        snapshot = self.Log.get_attachment_snapshot('project.task', self.task.id, rev_after)
        entry = snapshot['files'][0]
        self.assertFalse(entry['is_historical_content'])
        self.assertEqual(entry['attachment_id'], attachment.id)
        self.assertEqual(attachment.raw, b'version two')

    def test_replaced_content_is_parked_on_the_log_row(self):
        attachment = self._upload(name='spec.pdf', raw=b'version one')
        self.env.cr.precommit.run()
        attachment.write({'raw': b'version two'})

        log = self._logs(attachment, 'replaced')
        self.assertTrue(log.previous_attachment_id)
        self.assertEqual(log.previous_attachment_id.raw, b'version one')
        self.assertEqual(log.previous_attachment_id.res_model, 'project.attachment.log')
        self.assertEqual(log.previous_attachment_id.res_id, log.id)
        self.assertFalse(
            self._logs(log.previous_attachment_id),
            "parking a copy must not be audited as a new upload")

    def test_history_lists_every_event_newest_first(self):
        a = self._upload(name='a.pdf')
        self.env.cr.precommit.run()
        a._delete_and_notify()

        history = self.Log.get_attachment_history('project.task', self.task.id)
        self.assertEqual([r['action'] for r in history['revisions']], ['deleted', 'added'])
        self.assertTrue(all(r['summary'] for r in history['revisions']))
        self.assertEqual(history['record']['display_name'], self.task.display_name)
        self.assertTrue(history['record']['create_date'])

    def test_deleted_file_keeps_a_usable_download(self):
        attachment = self._upload()
        self.env.cr.precommit.run()
        attachment._delete_and_notify()
        rev_add = self._logs(attachment, 'added').id

        snapshot = self.Log.with_user(self.user_manager).get_attachment_snapshot(
            'project.task', self.task.id, rev_add)
        data = snapshot['store_data']['ir.attachment'][0]
        self.assertEqual(data['id'], attachment.id)
        self.assertTrue(data.get('raw_access_token'), "the download needs a token")
        # The parked file must remain readable through the log record.
        self.assertTrue(
            self.env['ir.attachment'].with_user(self.user_manager).browse(attachment.id).has_access('read'))

    def test_history_requires_read_access_on_the_record(self):
        """ The public methods take arbitrary arguments, so they must check.

        A default project is visible to every employee, hence the private one:
        the guard is only observable on a record the user really cannot read.
        """
        private_project = self.env['project.project'].create({
            'name': 'Private Project',
            'privacy_visibility': 'followers',
        })
        private_task = self.env['project.task'].create({
            'name': 'Private Task',
            'project_id': private_project.id,
        })
        self._upload(record=private_task)
        self.env.cr.precommit.run()

        # Sanity check: the plain employee cannot reach the task itself.
        with self.assertRaises(AccessError):
            private_task.with_user(self.user_outsider).check_access('read')

        with self.assertRaises(AccessError):
            self.Log.with_user(self.user_outsider).get_attachment_history(
                'project.task', private_task.id)
        with self.assertRaises(AccessError):
            self.Log.with_user(self.user_outsider).get_attachment_snapshot(
                'project.task', private_task.id, -1)

        # ... while somebody who can read it gets the history.
        history = self.Log.with_user(self.user_manager).get_attachment_history(
            'project.task', private_task.id)
        self.assertEqual(len(history['revisions']), 1)

    def test_history_rejects_untracked_models(self):
        with self.assertRaises(UserError):
            self.Log.get_attachment_history('res.partner', self.env.user.partner_id.id)
        with self.assertRaises(UserError):
            self.Log.get_attachment_snapshot('res.partner', self.env.user.partner_id.id, -1)
        with self.assertRaises(UserError):
            self.Log.action_restore_snapshot('res.partner', self.env.user.partner_id.id, 1)

    # ------------------------------------------------------------
    # Snapshot restore
    # ------------------------------------------------------------

    def test_restore_snapshot_reverts_the_whole_set(self):
        kept = self._upload(name='kept.pdf', raw=b'kept')
        removed = self._upload(name='removed.pdf', raw=b'removed')
        self.env.cr.precommit.run()
        rev = self._logs(removed, 'added').id

        removed._delete_and_notify()
        added_later = self._upload(name='later.pdf', raw=b'later')
        self.env.cr.precommit.run()
        self.assertEqual(self._snapshot_names(-1), ['kept.pdf', 'later.pdf'])

        self.Log.action_restore_snapshot('project.task', self.task.id, rev)

        self.assertEqual(
            sorted(self._thread_attachments().mapped('name')), ['kept.pdf', 'removed.pdf'])
        self.assertTrue(self._logs(removed, 'restored'), "the restore is audited")
        self.assertTrue(self._logs(added_later, 'deleted'), "so is the removal")
        self.assertTrue(added_later.exists(), "and it is only a soft delete")

    def test_restore_snapshot_is_idempotent(self):
        self._upload(name='kept.pdf')
        removed = self._upload(name='removed.pdf', raw=b'removed')
        self.env.cr.precommit.run()
        rev = self._logs(removed, 'added').id
        removed._delete_and_notify()

        self.Log.action_restore_snapshot('project.task', self.task.id, rev)
        first = sorted(self._thread_attachments().mapped('name'))
        count = len(self.Log.search([('task_id', '=', self.task.id)]))

        self.Log.action_restore_snapshot('project.task', self.task.id, rev)
        self.assertEqual(sorted(self._thread_attachments().mapped('name')), first)
        self.assertEqual(
            len(self.Log.search([('task_id', '=', self.task.id)])), count,
            "a no-op restore must not write any event")

    def test_restore_snapshot_requires_write_access(self):
        attachment = self._upload()
        self.env.cr.precommit.run()
        rev = self._logs(attachment, 'added').id
        with self.assertRaises(AccessError):
            self.Log.with_user(self.user_outsider).action_restore_snapshot(
                'project.task', self.task.id, rev)

    # ------------------------------------------------------------
    # Backfill
    # ------------------------------------------------------------

    def test_backfill_logs_pre_existing_files_only_once(self):
        from odoo.addons.project_attachment_history import _backfill_attachment_history

        # A file that predates the module: created without the audit running.
        legacy = self.env['ir.attachment'].with_context(
            project_attachment_no_log=True).create({
                'name': 'legacy.pdf',
                'raw': b'legacy',
                'res_model': 'project.task',
                'res_id': self.task.id,
            })
        tracked = self._upload(name='tracked.pdf')
        self.env.cr.precommit.run()
        self.assertFalse(self._logs(legacy))

        _backfill_attachment_history(self.env)

        log = self._logs(legacy, 'added')
        self.assertEqual(len(log), 1)
        self.assertEqual(log.date, legacy.create_date, "dated from the file itself")
        self.assertEqual(log.user_id, legacy.create_uid)
        self.assertEqual(len(self._logs(tracked, 'added')), 1, "no duplicate for logged files")

        _backfill_attachment_history(self.env)
        self.assertEqual(len(self._logs(legacy, 'added')), 1, "running it twice changes nothing")

    # ------------------------------------------------------------
    # Access
    # ------------------------------------------------------------

    @users('attachment_manager')
    def test_manager_can_read_history(self):
        attachment = self._upload()
        self.env.cr.precommit.run()
        self.assertTrue(self.env['project.attachment.log'].search(
            [('attachment_id', '=', attachment.id)]))

    def test_nobody_can_write_history(self):
        attachment = self._upload()
        self.env.cr.precommit.run()
        log = self._logs(attachment, 'added')
        with self.assertRaises(AccessError):
            log.with_user(self.user_manager).write({'attachment_name': 'forged.pdf'})

    def test_base64_upload_is_logged(self):
        """ The portal and the mail gateway create attachments from `datas`. """
        attachment = self.env['ir.attachment'].create({
            'name': 'from_portal.pdf',
            'datas': base64.b64encode(b'portal content'),
            'res_model': 'project.task',
            'res_id': self.task.id,
        })
        self.env.cr.precommit.run()
        self.assertEqual(len(self._logs(attachment, 'added')), 1)
