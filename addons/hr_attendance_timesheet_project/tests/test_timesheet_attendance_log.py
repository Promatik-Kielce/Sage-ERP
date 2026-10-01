from datetime import datetime

from odoo.tests import tagged

from .common import TimesheetAttendanceCommon


@tagged('post_install', '-at_install')
class TestTimesheetAttendanceLog(TimesheetAttendanceCommon):

    @classmethod
    def _timesheet_notes(cls, attendance):
        return attendance.message_ids.filtered(lambda message: 'Timesheet' in str(message.body))

    def _new_notes(self, attendance, before):
        return self._timesheet_notes(attendance) - before

    def test_edit_logs_old_and_new_values(self):
        before = self._timesheet_notes(self.attendance)
        self.line.write({'unit_amount': 2.5, 'project_id': self.other_project.id})
        notes = self._new_notes(self.attendance, before)
        self.assertEqual(len(notes), 1)
        body = str(notes.body)
        self.assertIn('Timesheet changed', body)
        self.assertIn('04:00', body)
        self.assertIn('02:30', body)
        self.assertIn(self.project.name, body)
        self.assertIn(self.other_project.name, body)

    def test_edit_without_visible_change_logs_nothing(self):
        before = self._timesheet_notes(self.attendance)
        self.line.write({'unit_amount': 4.0, 'name': 'Linked work'})
        self.assertFalse(self._new_notes(self.attendance, before))

    def test_untracked_field_change_logs_nothing(self):
        before = self._timesheet_notes(self.attendance)
        self.line.write({'amount': -42.0})
        self.assertFalse(self._new_notes(self.attendance, before))

    def test_add_logs_note(self):
        before = self._timesheet_notes(self.attendance)
        self.env['account.analytic.line'].create(self._line_vals(self.attendance, name='Late addition', hours=1.5))
        notes = self._new_notes(self.attendance, before)
        self.assertEqual(len(notes), 1)
        self.assertIn('Timesheet added', str(notes.body))
        self.assertIn('Late addition', str(notes.body))
        self.assertIn('01:30', str(notes.body))

    def test_delete_logs_note(self):
        before = self._timesheet_notes(self.attendance)
        self.line.unlink()
        notes = self._new_notes(self.attendance, before)
        self.assertEqual(len(notes), 1)
        self.assertIn('Timesheet removed', str(notes.body))
        self.assertIn('Linked work', str(notes.body))

    def test_moving_to_other_attendance_logs_on_both(self):
        other_attendance = self._create_attendance(
            self.employee, check_in=datetime(2026, 1, 5, 17, 0), check_out=datetime(2026, 1, 5, 22, 0))
        before_old = self._timesheet_notes(self.attendance)
        before_new = self._timesheet_notes(other_attendance)
        self.line.write({'attendance_id': other_attendance.id})
        self.assertIn('Timesheet removed', str(self._new_notes(self.attendance, before_old).body))
        self.assertIn('Timesheet added', str(self._new_notes(other_attendance, before_new).body))

    def test_note_author_is_the_editing_user(self):
        before = self._timesheet_notes(self.attendance)
        self.line.with_user(self.user_attendance_admin).write({'unit_amount': 3.0})
        notes = self._new_notes(self.attendance, before)
        self.assertEqual(notes.author_id, self.user_attendance_admin.partner_id)
        self.assertEqual(notes.message_type, 'notification')

    def test_check_in_and_check_out_are_not_logged(self):
        employee = self.env['hr.employee'].create({'name': 'Clocking Employee'})
        attendance = employee.sudo()._attendance_action_change()
        self.assertTrue(attendance.timesheet_ids, "Check-in should open a timesheet")
        employee.sudo()._attendance_action_change()
        self.assertTrue(attendance.check_out)
        self.assertFalse(self._timesheet_notes(attendance))

    def test_project_switch_is_not_logged(self):
        employee = self.env['hr.employee'].create({'name': 'Switching Employee'})
        attendance = employee.sudo()._attendance_action_change()
        attendance.change_project_to(self.other_project.id)
        self.assertEqual(len(attendance.timesheet_ids), 2)
        self.assertFalse(self._timesheet_notes(attendance))

    def test_rebalance_after_check_out_edit_is_logged(self):
        before = self._timesheet_notes(self.attendance)
        self.attendance.with_user(self.user_attendance_admin).write({'check_out': datetime(2026, 1, 5, 14, 0)})
        self.assertEqual(self.line.unit_amount, 2.0)
        notes = self._new_notes(self.attendance, before)
        self.assertEqual(len(notes), 1)
        self.assertIn('04:00', str(notes.body))
        self.assertIn('02:00', str(notes.body))
