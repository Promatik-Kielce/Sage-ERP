from datetime import datetime

from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.custom_hr_attendance_multi_manager.hooks import post_init_hook

OFFICER = "hr_attendance.group_hr_attendance_officer"


@tagged("post_install", "-at_install")
class TestAttendanceMultiManager(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Plain internal users (no HR rights): hr.employee searches get redirected to hr.employee.public.
        cls.user_primary = new_test_user(cls.env, login="att_mm_primary", groups="base.group_user")
        cls.user_secondary = new_test_user(cls.env, login="att_mm_secondary", groups="base.group_user")
        cls.user_other = new_test_user(cls.env, login="att_mm_other", groups=f"base.group_user,{OFFICER}")

        Employee = cls.env["hr.employee"]
        cls.emp_primary = Employee.create({"name": "Primary Manager", "user_id": cls.user_primary.id})
        cls.emp_secondary = Employee.create({"name": "Secondary Manager", "user_id": cls.user_secondary.id})
        Employee.create({"name": "Other Officer", "user_id": cls.user_other.id})
        cls.employee = Employee.create({"name": "Team Member"})
        cls.outsider = Employee.create({"name": "Outsider"})

        Rel = cls.env["hr.employee.manager.rel"]
        Rel.create({"employee_id": cls.employee.id, "manager_id": cls.emp_primary.id, "is_primary": True})
        cls.rel_secondary = Rel.create({"employee_id": cls.employee.id, "manager_id": cls.emp_secondary.id})

        Attendance = cls.env["hr.attendance"]
        cls.attendance = Attendance.create({
            "employee_id": cls.employee.id,
            "check_in": datetime(2026, 1, 5, 8, 0),
            "check_out": datetime(2026, 1, 5, 16, 0),
        })
        cls.outsider_attendance = Attendance.create({
            "employee_id": cls.outsider.id,
            "check_in": datetime(2026, 1, 5, 8, 0),
            "check_out": datetime(2026, 1, 5, 16, 0),
        })

    def _visible_attendances(self, user):
        return self.env["hr.attendance"].with_user(user).search([
            ("id", "in", (self.attendance | self.outsider_attendance).ids),
        ])

    def test_managers_get_officer_group(self):
        self.assertEqual(self.employee.parent_id, self.emp_primary)
        self.assertTrue(self.user_primary.has_group(OFFICER))
        self.assertTrue(self.user_secondary.has_group(OFFICER))

    def test_primary_and_secondary_see_team_attendances(self):
        self.assertEqual(self._visible_attendances(self.user_primary), self.attendance)
        self.assertEqual(self._visible_attendances(self.user_secondary), self.attendance)

    def test_unrelated_officer_does_not_see_team_attendances(self):
        self.assertFalse(self._visible_attendances(self.user_other))

    def test_secondary_manager_can_edit_team_attendance(self):
        self.attendance.with_user(self.user_secondary).write({"check_out": datetime(2026, 1, 5, 17, 0)})
        self.assertEqual(self.attendance.check_out, datetime(2026, 1, 5, 17, 0))

    def test_my_team_filter_and_employee_search(self):
        my_team = self.env["hr.attendance"].with_user(self.user_secondary).search([
            "|",
            ("employee_id.parent_id.user_id", "=", self.user_secondary.id),
            ("employee_id.x_is_managed_by_me", "=", True),
        ])
        self.assertEqual(my_team, self.attendance)

        Employee = self.env["hr.employee"].with_user(self.user_secondary)
        managed = Employee.search([("x_is_managed_by_me", "=", True)])
        self.assertEqual(managed, self.employee)
        self.assertNotIn(self.employee, Employee.search([("x_is_managed_by_me", "=", False)]))

    def test_gantt_rows_include_secondary_team(self):
        Attendance = self.env["hr.attendance"].with_user(self.user_secondary).with_context(
            allowed_company_ids=self.env.company.ids,
            gantt_start_date="2026-01-01",
        )
        rows = Attendance._read_group_employee_id(self.env["hr.employee"], [])
        self.assertIn(self.employee, rows)
        self.assertNotIn(self.outsider, rows)

    def test_inactive_relation_revokes_access(self):
        self.rel_secondary.active = False
        self.assertFalse(self._visible_attendances(self.user_secondary))
        self.assertEqual(self._visible_attendances(self.user_primary), self.attendance)

    def test_clean_attendance_officers_keeps_managers(self):
        user_approver = new_test_user(self.env, login="att_mm_approver", groups="base.group_user")
        for user in (self.user_secondary, user_approver):
            self.outsider.attendance_manager_id = user
            self.outsider.attendance_manager_id = self.user_other
        # Still a secondary manager of self.employee: keeps the group.
        self.assertTrue(self.user_secondary.has_group(OFFICER))
        # Manages nobody: standard hr_attendance cleanup still applies.
        self.assertFalse(user_approver.has_group(OFFICER))

    def test_manager_linked_to_user_later_gets_officer_group(self):
        manager = self.env["hr.employee"].create({"name": "Manager Without User"})
        self.env["hr.employee.manager.rel"].create({"employee_id": self.outsider.id, "manager_id": manager.id})
        user = new_test_user(self.env, login="att_mm_late", groups="base.group_user")
        manager.user_id = user
        self.assertTrue(user.has_group(OFFICER))

    def test_post_init_hook_backfills_officer_group(self):
        self.user_secondary.group_ids -= self.env.ref(OFFICER)
        self.assertFalse(self.user_secondary.has_group(OFFICER))
        post_init_hook(self.env)
        self.assertTrue(self.user_secondary.has_group(OFFICER))
