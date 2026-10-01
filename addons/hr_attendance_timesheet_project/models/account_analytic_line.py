# -*- coding: utf-8 -*-

from collections import defaultdict

from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import format_date, format_duration

# Import tolerance constant from hr_attendance extension
from .hr_attendance import TIMESHEET_TOLERANCE_HOURS

# Timesheet fields whose changes are logged in the chatter of the linked attendance
ATTENDANCE_LOGGED_FIELDS = ('date', 'project_id', 'task_id', 'name', 'unit_amount')
# Context keys disabling that log: ours marks the automatic check-in/check-out bookkeeping
ATTENDANCE_NO_LOG_CONTEXT_KEYS = ('attendance_timesheet_no_log', 'tracking_disable', 'mail_notrack')


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    attendance_id = fields.Many2one(
        'hr.attendance',
        string='Attendance',
        index=True,
        help="Link to the attendance record that generated this timesheet entry",
        ondelete='cascade',
    )

    def _compute_calendar_display_name(self):
        """Override to include employee name in calendar view for managers"""
        super()._compute_calendar_display_name()
        for line in self:
            if line.calendar_display_name and line.employee_id:
                # Append employee name: "Project (8h) - Employee Name"
                line.calendar_display_name = f"{line.calendar_display_name} - {line.employee_id.name}"

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to auto-set employee_id and user_id from attendance"""
        for vals in vals_list:
            if vals.get('attendance_id') and not vals.get('employee_id'):
                attendance = self.env['hr.attendance'].browse(vals['attendance_id'])
                if attendance.employee_id:
                    vals['employee_id'] = attendance.employee_id.id
                    # Also set user_id from employee
                    if attendance.employee_id.user_id and not vals.get('user_id'):
                        vals['user_id'] = attendance.employee_id.user_id.id
        lines = super().create(vals_list)
        if not lines._attendance_log_disabled():
            self._attendance_log_post(lines._attendance_log_line_entries(_("Timesheet added")))
        return lines

    def write(self, vals):
        log = not self._attendance_log_disabled() and any(
            fname in vals for fname in ATTENDANCE_LOGGED_FIELDS + ('attendance_id',)
        )
        before = self._attendance_log_snapshot() if log else {}

        result = super().write(vals)

        # _check_access() ran on the values before the write: check again when the
        # attendance or the project changed, as it may move the line out of reach.
        if 'attendance_id' in vals or 'project_id' in vals:
            self.check_access('write')

        if log:
            self._attendance_log_changes(before)
        return result

    def unlink(self):
        entries = {}
        if not self._attendance_log_disabled():
            entries = self._attendance_log_line_entries(_("Timesheet removed"))
        result = super().unlink()
        self._attendance_log_post(entries)
        return result

    # ------------------------------------------------------------
    # Access rights
    # ------------------------------------------------------------

    def _check_access(self, operation):
        """ Timesheets linked to an attendance can be created, changed and deleted by
        exactly the users who can change that attendance. The other timesheets only by
        Timesheets administrators.

        This cannot be done with record rules: the rules of different groups are OR-ed,
        so the project and hr_timesheet rules would still grant access. The rules in
        security/timesheet_security.xml only give attendance editors a way in.
        """
        result = super()._check_access(operation)
        if result or operation == 'read' or self.env.su:
            return result

        timesheets = self.sudo().browse([id_ for id_ in self._ids if id_]).filtered('project_id')
        linked = timesheets.filtered('attendance_id')
        writable_attendances = linked.attendance_id.with_env(self.env)._filtered_access('write')
        forbidden = linked.filtered(lambda line: line.attendance_id not in writable_attendances)
        if not self.env.user.has_group('hr_timesheet.group_timesheet_manager'):
            forbidden |= timesheets - linked
        if not forbidden:
            return None
        forbidden = forbidden.with_env(self.env)
        return forbidden, forbidden._make_timesheet_access_error

    def _make_timesheet_access_error(self):
        linked = self.sudo().filtered('attendance_id')
        if linked:
            return AccessError(_(
                "You cannot change the timesheets of %(employees)s: they belong to attendances "
                "you are not allowed to edit. Only the people who can edit an attendance can "
                "edit its timesheets.",
                employees=", ".join(linked.attendance_id.employee_id.mapped('name')),
            ))
        return AccessError(_(
            "Only Timesheets administrators can create, edit or delete timesheets "
            "that are not linked to an attendance."
        ))

    def _check_can_write(self, values):
        # Linked timesheets follow the rights on their attendance (see _check_access),
        # not hr_timesheet's "own timesheets only" restriction.
        unlinked = self.filtered(lambda line: not line.sudo().attendance_id)
        return super(AccountAnalyticLine, unlinked)._check_can_write(values)

    # ------------------------------------------------------------
    # Log in the attendance chatter
    # ------------------------------------------------------------

    def _attendance_log_disabled(self):
        return any(self.env.context.get(key) for key in ATTENDANCE_NO_LOG_CONTEXT_KEYS)

    def _attendance_log_labels(self):
        return {
            'date': _("Date"),
            'project_id': _("Project"),
            'task_id': _("Task"),
            'name': _("Description"),
            'unit_amount': _("Hours"),
        }

    def _attendance_log_snapshot(self):
        """ Return {line id: (attendance, {logged field: displayed value})}. """
        return {
            line.id: (line.attendance_id, {
                'date': format_date(self.env, line.date) if line.date else '',
                'project_id': line.project_id.display_name or '',
                'task_id': line.task_id.display_name or '',
                'name': line.name or '',
                'unit_amount': format_duration(line.unit_amount),
            })
            for line in self.sudo()
        }

    def _attendance_log_entry(self, title, values, changes=()):
        project = values['project_id']
        if values['task_id']:
            project = f"{project} / {values['task_id']}"
        entry = Markup("%s: <b>%s</b> · %s · %s · %s") % (
            title, project, values['date'], values['unit_amount'], values['name'],
        )
        if changes:
            entry += Markup("<ul>%s</ul>") % Markup().join(
                Markup("<li>%s: %s → %s</li>") % change for change in changes
            )
        return entry

    def _attendance_log_line_entries(self, title):
        """ Return {attendance: [one log line per timesheet of ``self`` linked to it]}. """
        entries = defaultdict(list)
        for attendance, values in self._attendance_log_snapshot().values():
            if attendance:
                entries[attendance].append(self._attendance_log_entry(title, values))
        return entries

    def _attendance_log_changes(self, before):
        """ Log the changes made since the snapshot ``before``, compared on the values
        written in database so that saves changing nothing visible are not logged. """
        labels = self._attendance_log_labels()
        entries = defaultdict(list)
        for line_id, (attendance, values) in self._attendance_log_snapshot().items():
            old_attendance, old_values = before[line_id]
            if old_attendance != attendance:
                if old_attendance:
                    entries[old_attendance].append(self._attendance_log_entry(_("Timesheet removed"), old_values))
                if attendance:
                    entries[attendance].append(self._attendance_log_entry(_("Timesheet added"), values))
                continue
            if not attendance:
                continue
            changes = [
                (labels[fname], old_values[fname], values[fname])
                for fname in ATTENDANCE_LOGGED_FIELDS
                if old_values[fname] != values[fname]
            ]
            if changes:
                entries[attendance].append(self._attendance_log_entry(_("Timesheet changed"), values, changes))
        self._attendance_log_post(entries)

    def _attendance_log_post(self, entries):
        """ Post one note per attendance, ``entries`` mapping attendances to log lines. """
        for attendance, attendance_entries in entries.items():
            if attendance.exists():
                attendance._message_log(body=Markup("<br/>").join(attendance_entries))

    @api.constrains('employee_id', 'attendance_id')
    def _check_employee_matches_attendance(self):
        """Ensure timesheet employee matches attendance employee"""
        for line in self:
            if line.attendance_id and line.employee_id:
                if line.employee_id != line.attendance_id.employee_id:
                    raise ValidationError(_(
                        "Timesheet employee (%(timesheet_emp)s) must match attendance employee (%(attendance_emp)s).\n\n"
                        "The timesheet is linked to an attendance for %(attendance_emp)s, "
                        "so the timesheet must also be for the same employee.",
                        timesheet_emp=line.employee_id.name,
                        attendance_emp=line.attendance_id.employee_id.name,
                    ))

    @api.constrains('date', 'attendance_id')
    def _check_date_matches_attendance(self):
        """Ensure timesheet date matches attendance date(s)

        For same-day attendances, timesheet must be on that date.
        For cross-day attendances (e.g., night shifts), timesheet can be on either date.
        """
        for line in self:
            if line.attendance_id and line.date:
                attendance = line.attendance_id

                if not attendance.check_in:
                    continue

                # Get attendance date range
                check_in_date = attendance.check_in.date()
                check_out_date = attendance.check_out.date() if attendance.check_out else check_in_date

                # Timesheet date must be within attendance date range (inclusive)
                if line.date < check_in_date or line.date > check_out_date:
                    # Build error message
                    if check_in_date == check_out_date:
                        raise ValidationError(_(
                            "Timesheet date (%(timesheet_date)s) must match attendance date (%(attendance_date)s).\n\n"
                            "This timesheet is linked to an attendance on %(attendance_date)s "
                            "(%(check_in)s to %(check_out)s).\n\n"
                            "Please change the timesheet date to %(attendance_date)s.",
                            timesheet_date=line.date,
                            attendance_date=check_in_date,
                            check_in=attendance.check_in,
                            check_out=attendance.check_out or _('ongoing'),
                        ))
                    else:
                        raise ValidationError(_(
                            "Timesheet date (%(timesheet_date)s) must be within attendance date range.\n\n"
                            "This timesheet is linked to an attendance that spans multiple days:\n"
                            "  Check-in: %(check_in)s (%(check_in_date)s)\n"
                            "  Check-out: %(check_out)s (%(check_out_date)s)\n\n"
                            "Timesheet date must be either %(check_in_date)s or %(check_out_date)s.",
                            timesheet_date=line.date,
                            check_in=attendance.check_in,
                            check_out=attendance.check_out or _('ongoing'),
                            check_in_date=check_in_date,
                            check_out_date=check_out_date,
                        ))

    @api.onchange('date')
    def _onchange_date_check_attendance(self):
        """Provide immediate feedback when changing timesheet date"""
        if self.attendance_id and self.date:
            attendance = self.attendance_id

            if not attendance.check_in:
                return

            # Get attendance date range
            check_in_date = attendance.check_in.date()
            check_out_date = attendance.check_out.date() if attendance.check_out else check_in_date

            # Check if date is outside attendance date range
            if self.date < check_in_date or self.date > check_out_date:
                if check_in_date == check_out_date:
                    return {
                        'warning': {
                            'title': _('Error: Invalid Date'),
                            'message': _(
                                'Timesheet date (%(timesheet_date)s) must match attendance date (%(attendance_date)s).\n\n'
                                'This timesheet is linked to an attendance on %(attendance_date)s '
                                '(%(check_in)s to %(check_out)s).\n\n'
                                'Please change the timesheet date to %(attendance_date)s.',
                                timesheet_date=self.date,
                                attendance_date=check_in_date,
                                check_in=attendance.check_in,
                                check_out=attendance.check_out or _('ongoing'),
                            )
                        }
                    }
                else:
                    return {
                        'warning': {
                            'title': _('Error: Invalid Date'),
                            'message': _(
                                'Timesheet date (%(timesheet_date)s) must be within attendance date range.\n\n'
                                'This timesheet is linked to an attendance that spans multiple days:\n'
                                '  Check-in: %(check_in)s (%(check_in_date)s)\n'
                                '  Check-out: %(check_out)s (%(check_out_date)s)\n\n'
                                'Timesheet date must be either %(check_in_date)s or %(check_out_date)s.',
                                timesheet_date=self.date,
                                check_in=attendance.check_in,
                                check_out=attendance.check_out or _('ongoing'),
                                check_in_date=check_in_date,
                                check_out_date=check_out_date,
                            )
                        }
                    }

    @api.onchange('unit_amount')
    def _onchange_unit_amount_check_attendance(self):
        """Provide immediate feedback when changing timesheet hours from attendance view"""
        if self.attendance_id and self.attendance_id.worked_hours and self.unit_amount:
            # Calculate what the total would be with this change
            # Sum other timesheets (excluding current line being edited) + current line's new value
            # This uses attendance.timesheet_ids which includes pending changes in the form
            other_timesheets_total = sum(
                line.unit_amount
                for line in self.attendance_id.timesheet_ids
                if line.id != self.id and line.id  # Exclude current line
            )
            new_total = other_timesheets_total + self.unit_amount
            max_allowed = self.attendance_id.worked_hours + TIMESHEET_TOLERANCE_HOURS

            if new_total > max_allowed:
                excess = new_total - self.attendance_id.worked_hours
                excess_min = int(excess * 60)

                # Block for everyone (no admin bypass)
                return {
                    'warning': {
                        'title': _('Error: Cannot exceed attendance hours'),
                        'message': _(
                            'Total timesheet hours (%(new_total)s h) cannot exceed attendance worked hours (%(worked)s h) by more than 15 minutes.\n\n'
                            'Attendance: %(check_in)s to %(check_out)s\n'
                            'Worked hours: %(worked)s h\n'
                            'Other timesheets: %(other)s h\n'
                            'This entry: %(current)s h\n'
                            'Total: %(new_total)s h\n'
                            'Maximum allowed: %(max)s h\n'
                            'Excess: %(excess)s h (%(excess_min)s min)\n\n'
                            'Please reduce the hours or adjust the attendance check-in/check-out times first.',
                            new_total=round(new_total, 2),
                            worked=round(self.attendance_id.worked_hours, 2),
                            other=round(other_timesheets_total, 2),
                            current=round(self.unit_amount, 2),
                            max=round(max_allowed, 2),
                            excess=round(excess, 2),
                            excess_min=excess_min,
                            check_in=self.attendance_id.check_in,
                            check_out=self.attendance_id.check_out,
                        )
                    }
                }

    @api.constrains('unit_amount', 'attendance_id')
    def _check_timesheet_not_exceed_attendance(self):
        """Prevent timesheet hours from exceeding attendance hours (with tolerance)

        This validation applies to everyone, including administrators.

        Note: This constraint is skipped when timesheets are edited via One2many
        from the attendance form, as it would check intermediate states during
        batch operations. The attendance-level validation handles those cases.
        """
        # Skip validation during One2many batch edits from attendance form
        if self.env.context.get('skip_timesheet_attendance_constraint'):
            return

        for line in self:
            if line.attendance_id and line.attendance_id.worked_hours:
                attendance = line.attendance_id
                # Calculate total timesheet hours for this attendance
                # Use attendance.timesheet_ids which includes pending changes in the current transaction
                # (e.g., when editing an attendance form with multiple timesheet changes at once)
                total_timesheet_hours = sum(attendance.timesheet_ids.mapped('unit_amount'))
                max_allowed = attendance.worked_hours + TIMESHEET_TOLERANCE_HOURS

                if total_timesheet_hours > max_allowed:
                    # Block for everyone (no admin bypass)
                    raise ValidationError(_(
                        "Total timesheet hours (%(timesheet)s h) cannot exceed attendance worked hours (%(attendance)s h) by more than %(tolerance)s minutes.\n\n"
                        "Attendance: %(check_in)s to %(check_out)s\n"
                        "Worked hours: %(attendance)s h\n"
                        "Total timesheets: %(timesheet)s h\n"
                        "Excess: %(excess)s h (%(excess_min)s min)\n\n"
                        "To fix this, you must either:\n"
                        "1. Reduce the timesheet hours, OR\n"
                        "2. Adjust the attendance check-in/check-out times to increase worked hours",
                        timesheet=round(total_timesheet_hours, 2),
                        attendance=round(attendance.worked_hours, 2),
                        tolerance=int(TIMESHEET_TOLERANCE_HOURS * 60),
                        check_in=attendance.check_in,
                        check_out=attendance.check_out,
                        excess=round(total_timesheet_hours - attendance.worked_hours, 2),
                        excess_min=int((total_timesheet_hours - attendance.worked_hours) * 60),
                    ))
