# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

TIMESHEET_TOLERANCE_HOURS = 0.25


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    project_id = fields.Many2one(
        'project.project',
        string='Business Trip Project',
        index=True,
        help="Project assigned to this attendance.",
    )

    timesheet_ids = fields.One2many(
        'account.analytic.line',
        'attendance_id',
        string='Timesheets',
        help="Timesheet entries generated from this attendance"
    )
    active_timesheet_id = fields.Many2one(
        'account.analytic.line',
        string='Active Timesheet',
        help="Currently active timesheet entry (not yet closed)"
    )
    current_project_id = fields.Many2one(
        'project.project',
        string='Current Project',
        compute='_compute_current_project',
        store=False,
        help="Project from the active timesheet"
    )
    main_project_id = fields.Many2one(
        'project.project',
        string='Main Project',
        compute='_compute_main_project',
        store=True,
        help="Project with the most timesheet hours in this attendance"
    )
    total_timesheet_hours = fields.Float(
        string='Total Timesheet Hours',
        compute='_compute_timesheet_hours',
        store=True,
        help="Sum of all timesheet hours for this attendance"
    )
    timesheet_hours_diff = fields.Float(
        string='Hours Difference',
        compute='_compute_timesheet_hours',
        store=True,
        help="Difference between timesheet hours and worked hours (positive = excess, negative = missing)"
    )
    ignore_negative_expected_hours = fields.Boolean(
        related='employee_id.ignore_negative_expected_hours',
        readonly=True,
    )

    @api.depends('active_timesheet_id', 'active_timesheet_id.project_id')
    def _compute_current_project(self):
        for attendance in self:
            attendance.current_project_id = attendance.active_timesheet_id.project_id if attendance.active_timesheet_id else False

    @api.depends('timesheet_ids.unit_amount', 'timesheet_ids.project_id')
    def _compute_main_project(self):
        for attendance in self:
            if not attendance.timesheet_ids:
                attendance.main_project_id = False
                continue

            hours_by_project = {}
            for timesheet in attendance.timesheet_ids:
                project = timesheet.project_id
                if not project:
                    continue
                if project not in hours_by_project:
                    hours_by_project[project] = 0.0
                hours_by_project[project] += timesheet.unit_amount

            if not hours_by_project:
                attendance.main_project_id = False
                continue

            attendance.main_project_id = max(hours_by_project, key=hours_by_project.get)

    @api.depends('timesheet_ids.unit_amount', 'worked_hours')
    def _compute_timesheet_hours(self):
        for attendance in self:
            total = sum(attendance.timesheet_ids.mapped('unit_amount'))
            attendance.total_timesheet_hours = total
            if attendance.worked_hours:
                attendance.timesheet_hours_diff = total - attendance.worked_hours
            else:
                attendance.timesheet_hours_diff = 0.0

    @api.model
    def create(self, vals):
        attendance = super().create(vals)

        # Only create timesheet on check-in (check_out is empty)
        if not attendance.check_out:
            attendance._create_initial_timesheet()

        return attendance

    def write(self, vals):
        old_values = {}
        if 'check_in' in vals or 'check_out' in vals:
            for attendance in self:
                old_values[attendance.id] = {
                    'check_in': attendance.check_in,
                    'check_out': attendance.check_out,
                    'worked_hours': attendance.worked_hours,
                }

        if 'timesheet_ids' in vals:
            result = super(HrAttendance, self.with_context(skip_timesheet_attendance_constraint=True)).write(vals)
        else:
            result = super().write(vals)

        if 'check_out' in vals and vals['check_out']:
            for attendance in self:
                old_val = old_values.get(attendance.id, {})
                if not old_val.get('check_out'):
                    if attendance.active_timesheet_id:
                        attendance._close_active_timesheet()
                    attendance._auto_fill_timesheet_gaps()

        if ('check_in' in vals or 'check_out' in vals) and old_values:
            for attendance in self:
                old_val = old_values.get(attendance.id, {})
                if old_val.get('check_out') and attendance.timesheet_ids:
                    old_worked_hours = old_val.get('worked_hours', 0.0)
                    new_worked_hours = attendance.worked_hours
                    if abs(new_worked_hours - old_worked_hours) > 0.01:
                        attendance._adjust_timesheets_to_worked_hours(
                            old_hours=old_worked_hours,
                            new_hours=new_worked_hours
                        )

        if ('check_in' in vals or 'check_out' in vals) and old_values:
            for attendance in self:
                old_val = old_values.get(attendance.id, {})
                if old_val.get('check_out') and attendance.timesheet_ids:
                    attendance._validate_timesheet_hours_on_edit()

        return result

    def _create_initial_timesheet(self):
        self.ensure_one()

        if not self.employee_id:
            return

        project = self.employee_id.last_project_id or self._get_default_project()

        if not project:
            raise UserError(_("No default project found. Please configure a default project in Settings."))

        timesheet = self.env['account.analytic.line'].create({
            'employee_id': self.employee_id.id,
            'user_id': self.employee_id.user_id.id if self.employee_id.user_id else self.env.user.id,
            'project_id': project.id,
            'date': self.check_in.date(),
            'name': _('Work on %s') % project.name,
            'unit_amount': 0.0,
            'attendance_id': self.id,
        })

        self.active_timesheet_id = timesheet
        self.employee_id.last_project_id = project

    def _close_active_timesheet(self):
        self.ensure_one()

        if not self.active_timesheet_id:
            return

        end_time = self.check_out or fields.Datetime.now()
        start_time = self.check_in
        timesheet_start = start_time

        all_timesheets = self.timesheet_ids.sorted('create_date')
        if len(all_timesheets) > 1:
            active_index = None
            for idx, ts in enumerate(all_timesheets):
                if ts.id == self.active_timesheet_id.id:
                    active_index = idx
                    break

            if active_index is not None and active_index > 0:
                previous_hours = sum(all_timesheets[:active_index].mapped('unit_amount'))
                from datetime import timedelta
                timesheet_start = start_time + timedelta(hours=previous_hours)

        duration = end_time - timesheet_start
        hours = duration.total_seconds() / 3600.0

        self.active_timesheet_id.write({
            'unit_amount': hours,
        })

        self.active_timesheet_id = False

    def action_change_project(self):
        self.ensure_one()

        if self.check_out:
            raise UserError(_("Cannot change project after check-out."))

        current_project_id = self.active_timesheet_id.project_id.id if self.active_timesheet_id and self.active_timesheet_id.project_id else False

        return {
            'name': _('Change Project'),
            'type': 'ir.actions.act_window',
            'res_model': 'attendance.change.project.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_attendance_id': self.id,
                'default_current_project_id': current_project_id,
            },
        }

    def change_project_to(self, new_project_id):
        self.ensure_one()

        if self.check_out:
            raise UserError(_("Cannot change project after check-out."))

        new_project = self.env['project.project'].browse(new_project_id)

        if not new_project.allow_timesheets:
            raise UserError(_("Selected project does not allow timesheets."))

        if self.active_timesheet_id:
            self._close_active_timesheet()

        timesheet = self.env['account.analytic.line'].create({
            'employee_id': self.employee_id.id,
            'user_id': self.employee_id.user_id.id if self.employee_id.user_id else self.env.user.id,
            'project_id': new_project.id,
            'date': self.check_in.date(),
            'name': _('Work on %s') % new_project.name,
            'unit_amount': 0.0,
            'attendance_id': self.id,
        })

        self.active_timesheet_id = timesheet
        self.employee_id.last_project_id = new_project

    def _get_default_project(self):
        default_project = self.env.ref('hr_attendance_timesheet_project.project_koszty_stale', raise_if_not_found=False)

        if not default_project:
            default_project = self.env['project.project'].search([
                ('name', '=', '0 - Koszty Stałe'),
                ('allow_timesheets', '=', True),
            ], limit=1)

        return default_project

    def _auto_fill_timesheet_gaps(self):
        self.ensure_one()

        if not self.worked_hours or not self.check_out:
            return

        gap_hours = self.worked_hours - self.total_timesheet_hours

        if abs(gap_hours) <= TIMESHEET_TOLERANCE_HOURS:
            if gap_hours != 0 and self.timesheet_ids:
                last_timesheet = self.timesheet_ids.sorted('create_date', reverse=True)[0]
                new_amount = last_timesheet.unit_amount + gap_hours
                if new_amount > 0:
                    last_timesheet.write({'unit_amount': new_amount})
            return

        if gap_hours > TIMESHEET_TOLERANCE_HOURS:
            default_project = self._get_default_project()
            if not default_project:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Timesheet Gap Detected'),
                        'message': _('Missing %.2f hours of timesheets, but no default project found to auto-fill.') % gap_hours,
                        'type': 'warning',
                        'sticky': False,
                    }
                }

            self.env['account.analytic.line'].create({
                'employee_id': self.employee_id.id,
                'user_id': self.employee_id.user_id.id if self.employee_id.user_id else self.env.user.id,
                'project_id': default_project.id,
                'date': self.check_in.date(),
                'name': _('Auto-filled unassigned time'),
                'unit_amount': gap_hours,
                'attendance_id': self.id,
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Timesheet Auto-Filled'),
                    'message': _('Added %.2f hours to "%s" project for untracked time.') % (gap_hours, default_project.name),
                    'type': 'info',
                    'sticky': False,
                }
            }

    def _reduce_timesheet_hours(self, timesheets, hours_to_remove):
        remaining_to_remove = hours_to_remove
        timesheets_to_delete = self.env['account.analytic.line']

        for timesheet in timesheets:
            if remaining_to_remove <= 0.01:
                break

            current_hours = timesheet.unit_amount

            if current_hours <= remaining_to_remove:
                timesheets_to_delete |= timesheet
                remaining_to_remove -= current_hours
            else:
                new_hours = current_hours - remaining_to_remove
                timesheet.write({'unit_amount': new_hours})
                remaining_to_remove = 0

        if timesheets_to_delete:
            timesheets_to_delete.unlink()

    def _increase_timesheet_hours(self, timesheets, hours_to_add):
        if not timesheets:
            return

        most_recent = timesheets[0]
        new_hours = most_recent.unit_amount + hours_to_add
        most_recent.write({'unit_amount': new_hours})

    def _adjust_timesheets_to_worked_hours(self, old_hours, new_hours):
        self.ensure_one()

        active_ts_id = self.active_timesheet_id.id if self.active_timesheet_id else False
        timesheets = self.timesheet_ids.filtered(
            lambda t: t.id != active_ts_id
        ).sorted(key=lambda t: t.create_date, reverse=True)

        if not timesheets:
            return

        adjustment = new_hours - old_hours

        if abs(adjustment) < 0.01:
            return

        if adjustment < 0:
            self._reduce_timesheet_hours(timesheets, abs(adjustment))
        else:
            self._increase_timesheet_hours(timesheets, adjustment)

    def _validate_timesheet_hours_on_edit(self):
        self.ensure_one()

        if not self.worked_hours:
            return

        total_timesheet_hours = sum(self.timesheet_ids.mapped('unit_amount'))
        max_allowed = self.worked_hours + TIMESHEET_TOLERANCE_HOURS

        if total_timesheet_hours > max_allowed:
            raise ValidationError(_(
                "Cannot save attendance changes: Total timesheet hours (%(timesheet)s h) exceed the new worked hours (%(worked)s h) by more than %(tolerance)s minutes.\n\n"
                "Current timesheets total: %(timesheet)s h\n"
                "New worked hours: %(worked)s h\n"
                "Maximum allowed: %(max)s h (with tolerance)\n"
                "Excess: %(excess)s h (%(excess_min)s min)\n\n"
                "To fix this, you must first reduce or delete timesheet entries before changing attendance times.",
                timesheet=round(total_timesheet_hours, 2),
                worked=round(self.worked_hours, 2),
                max=round(max_allowed, 2),
                tolerance=int(TIMESHEET_TOLERANCE_HOURS * 60),
                excess=round(total_timesheet_hours - self.worked_hours, 2),
                excess_min=int((total_timesheet_hours - self.worked_hours) * 60),
            ))