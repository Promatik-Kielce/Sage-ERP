from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class HrLeave(models.Model):
    _inherit = "hr.leave"

    def _is_user_employee_leave_approver(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        return self.employee_id._is_user_leave_approver(user)

    def _is_multi_approver_user(self, user=None):
        user = user or self.env.user
        return user.has_group("custom_hr_leave_multi_approver.group_timeoff_multi_approver")

    def _check_multi_approver_can_manage(self):
        """
        Użytkownik z grupą Time Off Multi Approver może zarządzać
        tylko urlopami pracowników, do których jest przypisany.
        """
        user = self.env.user

        # pełny HR manager zostaje bez ograniczeń
        if user.has_group("hr_holidays.group_hr_holidays_manager"):
            return

        # standardowy HR officer / responsible też zostaje bez ograniczeń
        if user.has_group("hr_holidays.group_hr_holidays_user"):
            return

        # nasz custom approver może działać tylko dla przypisanych pracowników
        if self._is_multi_approver_user(user):
            unauthorized = self.filtered(
                lambda leave: not leave.employee_id._is_user_leave_approver(user)
            )
            if unauthorized:
                raise AccessError(
                    _("You can only manage time off requests for employees assigned to you as Time Off Approver.")
                )
            return

        raise AccessError(_("You are not allowed to manage this time off request."))

    def _can_multi_approver_manage(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        return (
            self._is_multi_approver_user(user)
            and self.employee_id._is_user_leave_approver(user)
        )

    def _check_approval_update(self, state, raise_if_not_possible=True):
        user = self.env.user

        if user.has_group("hr_holidays.group_hr_holidays_manager") or user.has_group(
                "hr_holidays.group_hr_holidays_user"):
            return super()._check_approval_update(state, raise_if_not_possible=raise_if_not_possible)

        if self._is_multi_approver_user(user):
            unauthorized = self.filtered(
                lambda leave: not leave.employee_id._is_user_leave_approver(user)
            )

            if unauthorized:
                if raise_if_not_possible:
                    raise AccessError(
                        _("You can only manage time off requests for employees assigned to you as Time Off Approver.")
                    )
                return False

            # custom approver może:
            # - zrobić pierwszy approval
            # - odmówić
            # ale nie może zrobić finalnego validate
            if state in ("validate1", "refuse"):
                return True

            if state == "validate":
                if raise_if_not_possible:
                    raise AccessError(_("Only a Time Off Officer can apply final approval on a time off request."))
                return False

        return super()._check_approval_update(state, raise_if_not_possible=raise_if_not_possible)

    @api.depends_context("uid")
    def _compute_description(self):
        self.check_access("read")
        is_officer = self.env.user.has_group("hr_holidays.group_hr_holidays_user")

        for leave in self:
            if (
                is_officer
                or leave.user_id == self.env.user
                or leave._is_user_employee_leave_approver()
            ):
                leave.name = leave.sudo().private_name
            else:
                leave.name = "*****"

    def _inverse_description(self):
        is_officer = self.env.user.has_group("hr_holidays.group_hr_holidays_user")

        for leave in self:
            if (
                is_officer
                or leave.user_id == self.env.user
                or leave._is_user_employee_leave_approver()
            ):
                leave.sudo().private_name = leave.name

    def _get_employee_domain(self):
        domain = [
            ("active", "=", True),
            ("company_id", "in", self.env.companies.ids),
        ]
        if not self.env.user.has_group("hr_holidays.group_hr_holidays_user") and not self._is_multi_approver_user():
            domain += [
                ("user_id", "=", self.env.uid),
            ]
        elif self._is_multi_approver_user() and not self.env.user.has_group("hr_holidays.group_hr_holidays_user"):
            domain += [
                "|", "|",
                ("user_id", "=", self.env.uid),
                ("leave_manager_id", "=", self.env.uid),
                ("leave_manager_ids", "in", self.env.uid),
            ]
        return domain

    def _check_double_validation_rules(self, employees, state):
        user = self.env.user

        if user.has_group("hr_holidays.group_hr_holidays_manager"):
            return

        is_leave_user = user.has_group("hr_holidays.group_hr_holidays_user")
        is_multi_approver = user.has_group("custom_hr_leave_multi_approver.group_timeoff_multi_approver")

        if state == "validate1":
            employees = employees.filtered(
                lambda employee: not employee._is_user_leave_approver(user)
            )
            if employees and not (is_leave_user or is_multi_approver):
                raise AccessError(_(
                    "You cannot first approve a time off for %s, because you are not the employee's time off manager"
                ) % employees[0].name)

        elif state == "validate" and not is_leave_user:
            raise AccessError(_("You don't have the rights to apply second approval on a time off request"))

    def action_approve(self, check_state=True):
        self._check_multi_approver_can_manage()
        user = self.env.user

        # Custom approver: pierwszy krok dla typów z podwójną walidacją
        multi_first_level = self.filtered(
            lambda leave: (
                    self._is_multi_approver_user(user)
                    and leave.employee_id._is_user_leave_approver(user)
                    and leave.validation_type == "both"
                    and leave.state in ("confirm", "refuse")
                    and not user.has_group("hr_holidays.group_hr_holidays_user")
                    and not user.has_group("hr_holidays.group_hr_holidays_manager")
            )
        )

        remaining = self - multi_first_level

        if multi_first_level:
            if check_state:
                multi_first_level._check_approval_update("validate1", raise_if_not_possible=True)

            vals = {"state": "validate1"}
            if "first_approver_id" in self._fields:
                vals["first_approver_id"] = user.id

            multi_first_level.sudo().write(vals)

            if hasattr(multi_first_level, "activity_update"):
                multi_first_level.sudo().activity_update()

        if remaining:
            if self._is_multi_approver_user(user):
                return super(HrLeave, remaining.sudo()).action_approve(check_state=check_state)
            return super(HrLeave, remaining).action_approve(check_state=check_state)

        return True

    def action_validate(self, check_state=True):
        self._check_multi_approver_can_manage()

        if self._is_multi_approver_user():
            raise AccessError(_("Only a Time Off Officer can apply final approval on a time off request."))

        return super().action_validate(check_state=check_state)

    def action_refuse(self):
        self._check_multi_approver_can_manage()

        if self._is_multi_approver_user():
            if any(leave.state == "validate" for leave in self):
                raise AccessError(_("You cannot refuse a time off request after final approval."))

            return super(HrLeave, self.sudo()).action_refuse()

        return super().action_refuse()

    @api.depends("state", "employee_id", "employee_id.leave_manager_id", "employee_id.leave_manager_ids")
    @api.depends_context("uid")
    def _compute_can_refuse(self):
        super()._compute_can_refuse()
        user = self.env.user

        for leave in self:
            if leave._can_multi_approver_manage(user):
                leave.can_refuse = leave.state in ("confirm", "validate1")
            elif leave._is_multi_approver_user(user):
                leave.can_refuse = False

    def write(self, vals):
        is_officer = (
            self.env.user.has_group("hr_holidays.group_hr_holidays_user")
            or self.env.is_superuser()
        )
        is_multi_approver = self._is_multi_approver_user()

        protected_fields = {"attachment_ids", "supported_attachment_ids", "message_main_attachment_id"}

        if not is_officer and not is_multi_approver and (set(vals.keys()) - protected_fields):
            if any(
                hol.date_from
                and hol.date_from.date() < fields.Date.today()
                and not hol.employee_id._is_user_leave_approver(self.env.user)
                and hol.state not in ("confirm", "draft")
                for hol in self
            ):
                raise UserError(
                    _("You must have manager rights to modify/validate a time off that already begun")
                )

            if any(leave.state == "cancel" for leave in self):
                raise UserError(_("Only a manager can modify a canceled leave."))

        return super().write(vals)