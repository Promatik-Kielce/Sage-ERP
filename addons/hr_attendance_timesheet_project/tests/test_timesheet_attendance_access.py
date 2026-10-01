from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import TimesheetAttendanceCommon


@tagged('post_install', '-at_install')
class TestTimesheetAttendanceAccess(TimesheetAttendanceCommon):

    # Project administrators: read-only on timesheets

    def test_project_admin_cannot_edit_linked_timesheet(self):
        with self.assertRaises(AccessError):
            self.line.with_user(self.user_project_admin).write({'unit_amount': 3.0})

    def test_project_admin_cannot_delete_linked_timesheet(self):
        with self.assertRaises(AccessError):
            self.line.with_user(self.user_project_admin).unlink()

    def test_project_admin_cannot_create_unlinked_timesheet(self):
        with self.assertRaises(AccessError):
            self.env['account.analytic.line'].with_user(self.user_project_admin).create({
                'project_id': self.project.id,
                'employee_id': self.employee.id,
                'name': 'Sneaky entry',
                'unit_amount': 2.0,
            })

    def test_project_admin_cannot_edit_unlinked_timesheet(self):
        with self.assertRaises(AccessError):
            self.unlinked_line.with_user(self.user_project_admin).write({'unit_amount': 3.0})

    def test_project_admin_still_reads_all_timesheets(self):
        lines = self.env['account.analytic.line'].with_user(self.user_project_admin).search([
            ('id', 'in', (self.line | self.outsider_line | self.unlinked_line).ids),
        ])
        self.assertEqual(lines, self.line | self.outsider_line | self.unlinked_line)

    # Attendance officers: same rights as on the attendance

    def test_officer_can_edit_managed_timesheet(self):
        self.line.with_user(self.user_officer).write({'unit_amount': 3.0, 'project_id': self.other_project.id})
        self.assertEqual(self.line.unit_amount, 3.0)
        self.assertEqual(self.line.project_id, self.other_project)

    def test_officer_can_create_and_delete_managed_timesheet(self):
        Line = self.env['account.analytic.line'].with_user(self.user_officer)
        new_line = Line.create(self._line_vals(self.attendance))
        self.assertEqual(new_line.attendance_id, self.attendance)
        new_line.unlink()
        self.assertFalse(new_line.exists())

    def test_officer_can_edit_timesheets_from_attendance_form(self):
        self.attendance.with_user(self.user_officer).write({'timesheet_ids': [
            Command.update(self.line.id, {'unit_amount': 2.0}),
            Command.create(self._line_vals(self.attendance, name='Added from form')),
        ]})
        self.assertEqual(self.line.unit_amount, 2.0)
        self.assertIn('Added from form', self.attendance.timesheet_ids.mapped('name'))

    def test_officer_reads_managed_but_not_outsider_timesheets(self):
        lines = self.env['account.analytic.line'].with_user(self.user_officer).search([
            ('id', 'in', (self.line | self.outsider_line).ids),
        ])
        self.assertEqual(lines, self.line)

    def test_officer_cannot_edit_outsider_timesheet(self):
        with self.assertRaises(AccessError):
            self.outsider_line.with_user(self.user_officer).write({'unit_amount': 3.0})

    def test_timesheet_admin_cannot_attach_timesheet_to_attendance_they_cannot_edit(self):
        # The timesheet admin can edit the unlinked line and read their own attendance,
        # but not edit that attendance: the line must not end up linked to it.
        own_employee = self.env['hr.employee'].create({'name': 'Timesheet Admin', 'user_id': self.user_timesheet_admin.id})
        own_attendance = self._create_attendance(own_employee)
        own_line = self.env['account.analytic.line'].create({
            'project_id': self.project.id,
            'employee_id': own_employee.id,
            'name': 'Own manual entry',
            'unit_amount': 1.0,
            'date': own_attendance.check_in.date(),
        })
        with self.assertRaises(AccessError):
            own_line.with_user(self.user_timesheet_admin).write({'attendance_id': own_attendance.id})

    def test_analytic_line_cannot_become_unlinked_timesheet(self):
        user_analytic = new_test_user(
            self.env, login='ts_att_analytic', groups='base.group_user,analytic.group_analytic_accounting')
        plain_line = self.env['account.analytic.line'].create({
            'name': 'Plain analytic line',
            'amount': 10.0,
            'account_id': self.project.account_id.id,
            'user_id': user_analytic.id,
        })
        with self.assertRaises(AccessError):
            plain_line.with_user(user_analytic).write({'project_id': self.project.id})

    def test_officer_cannot_create_unlinked_timesheet(self):
        with self.assertRaises(AccessError):
            self.env['account.analytic.line'].with_user(self.user_officer).create({
                'project_id': self.project.id,
                'employee_id': self.emp_officer.id,
                'name': 'Unlinked entry',
                'unit_amount': 1.0,
            })

    # Timesheet administrators: unlinked timesheets only

    def test_timesheet_admin_can_edit_unlinked_timesheet(self):
        self.unlinked_line.with_user(self.user_timesheet_admin).write({'unit_amount': 2.0})
        self.assertEqual(self.unlinked_line.unit_amount, 2.0)

    def test_timesheet_admin_cannot_edit_linked_timesheet(self):
        with self.assertRaises(AccessError):
            self.line.with_user(self.user_timesheet_admin).write({'unit_amount': 3.0})

    # Attendance administrators: every linked timesheet

    def test_attendance_admin_can_edit_any_linked_timesheet(self):
        (self.line | self.outsider_line).with_user(self.user_attendance_admin).write({'unit_amount': 3.5})
        self.assertEqual((self.line | self.outsider_line).mapped('unit_amount'), [3.5, 3.5])
