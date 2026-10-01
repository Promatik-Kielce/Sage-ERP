from datetime import datetime

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestTimesheetMultiManager(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_secondary = new_test_user(cls.env, login="ts_mm_secondary", groups="base.group_user")
        cls.user_other = new_test_user(
            cls.env, login="ts_mm_other", groups="base.group_user,hr_attendance.group_hr_attendance_officer")

        Employee = cls.env["hr.employee"]
        emp_primary = Employee.create({"name": "Primary Manager"})
        emp_secondary = Employee.create({"name": "Secondary Manager", "user_id": cls.user_secondary.id})
        Employee.create({"name": "Other Officer", "user_id": cls.user_other.id})
        cls.employee = Employee.create({"name": "Team Member"})

        Rel = cls.env["hr.employee.manager.rel"]
        Rel.create({"employee_id": cls.employee.id, "manager_id": emp_primary.id, "is_primary": True})
        Rel.create({"employee_id": cls.employee.id, "manager_id": emp_secondary.id})

        project = cls.env["project.project"].create({"name": "Multi Manager Project", "allow_timesheets": True})
        attendance = cls.env["hr.attendance"].create({
            "employee_id": cls.employee.id,
            "check_in": datetime(2026, 1, 5, 8, 0),
            "check_out": datetime(2026, 1, 5, 16, 0),
        })
        cls.line = cls.env["account.analytic.line"].create({
            "attendance_id": attendance.id,
            "project_id": project.id,
            "name": "Team work",
            "unit_amount": 4.0,
            "date": attendance.check_in.date(),
        })

    def _visible_lines(self, user):
        return self.env["account.analytic.line"].with_user(user).search([("id", "=", self.line.id)])

    def test_secondary_manager_sees_and_edits_team_timesheet(self):
        self.assertEqual(self._visible_lines(self.user_secondary), self.line)
        self.line.with_user(self.user_secondary).write({"unit_amount": 3.0})
        self.assertEqual(self.line.unit_amount, 3.0)

    def test_unrelated_officer_cannot_see_or_edit_team_timesheet(self):
        self.assertFalse(self._visible_lines(self.user_other))
        with self.assertRaises(AccessError):
            self.line.with_user(self.user_other).write({"unit_amount": 3.0})
