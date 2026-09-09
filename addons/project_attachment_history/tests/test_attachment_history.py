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

        logs = self._logs(attachment, 'moved')
        self.assertEqual(len(logs), 2, "both the source and the target are audited")
        self.assertEqual(
            set(logs.mapped('res_id')), {self.task.id, other_task.id})

    def test_move_out_of_scope_is_logged(self):
        partner = self.env['res.partner'].create({'name': 'Somebody'})
        attachment = self._upload()
        self.env.cr.precommit.run()

        attachment.write({'res_model': 'res.partner', 'res_id': partner.id})

        logs = self._logs(attachment, 'moved')
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.res_model, 'project.task')
        self.assertEqual(logs.res_id, self.task.id)

    def test_detaching_the_file_entirely_is_logged(self):
        """ Emptying `res_model` must be audited, not crash. """
        attachment = self._upload()
        self.env.cr.precommit.run()

        attachment.write({'res_model': False, 'res_id': 0})

        logs = self._logs(attachment, 'moved')
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
