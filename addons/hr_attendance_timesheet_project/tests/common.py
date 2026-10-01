from datetime import date, datetime

from odoo.tests import new_test_user
from odoo.tests.common import TransactionCase


class TimesheetAttendanceCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Project = cls.env['project.project']
        cls.project = Project.create({
            'name': 'Attendance Access Project',
            'allow_timesheets': True,
            'privacy_visibility': 'employees',
        })
        cls.other_project = Project.create({
            'name': 'Attendance Access Other Project',
            'allow_timesheets': True,
            'privacy_visibility': 'employees',
        })

        cls.user_project_admin = new_test_user(
            cls.env, login='ts_att_project_admin', groups='base.group_user,project.group_project_manager')
        cls.user_officer = new_test_user(
            cls.env, login='ts_att_officer', groups='base.group_user,hr_attendance.group_hr_attendance_officer')
        cls.user_timesheet_admin = new_test_user(
            cls.env, login='ts_att_timesheet_admin', groups='base.group_user,hr_timesheet.group_timesheet_manager')
        cls.user_attendance_admin = new_test_user(
            cls.env, login='ts_att_attendance_admin', groups='base.group_user,hr_attendance.group_hr_attendance_user')

        Employee = cls.env['hr.employee']
        cls.emp_officer = Employee.create({'name': 'Officer', 'user_id': cls.user_officer.id})
        cls.employee = Employee.create({'name': 'Team Member', 'parent_id': cls.emp_officer.id})
        cls.outsider = Employee.create({'name': 'Outsider'})

        cls.attendance = cls._create_attendance(cls.employee)
        cls.outsider_attendance = cls._create_attendance(cls.outsider)
        cls.line = cls._create_line(cls.attendance, 'Linked work', 4.0)
        cls.outsider_line = cls._create_line(cls.outsider_attendance, 'Outsider work', 4.0)
        cls.unlinked_line = cls.env['account.analytic.line'].create({
            'project_id': cls.project.id,
            'employee_id': cls.employee.id,
            'name': 'Manual entry',
            'unit_amount': 1.0,
            'date': date(2026, 1, 5),
        })

    @classmethod
    def _create_attendance(cls, employee, check_in=datetime(2026, 1, 5, 8, 0), check_out=datetime(2026, 1, 5, 16, 0)):
        return cls.env['hr.attendance'].create({
            'employee_id': employee.id,
            'check_in': check_in,
            'check_out': check_out,
        })

    @classmethod
    def _create_line(cls, attendance, name, hours, project=None):
        return cls.env['account.analytic.line'].create({
            'attendance_id': attendance.id,
            'project_id': (project or cls.project).id,
            'name': name,
            'unit_amount': hours,
            'date': attendance.check_in.date(),
        })

    def _line_vals(self, attendance, name='New work', hours=1.0):
        return {
            'attendance_id': attendance.id,
            'employee_id': attendance.employee_id.id,
            'project_id': self.project.id,
            'name': name,
            'unit_amount': hours,
            'date': attendance.check_in.date(),
        }
