# Part of Odoo. See LICENSE file for full copyright and licensing details.

import math

import pytz
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, exceptions, _


def _round_half_hour(delta):
    """Round a float (hours) to the nearest 0.5h, rounding >= 0.25h away from zero.

    Deltas under 15 minutes (0.25h) from zero round to 0.
    Examples: +0.2 -> 0.0, +0.25 -> +0.5, +0.78 -> +1.0
    """
    if delta >= 0:
        return math.floor(delta * 2 + 0.5) / 2
    return -math.floor(-delta * 2 + 0.5) / 2


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    attendance_manager_id = fields.Many2one(
        'res.users', store=True, readonly=False,
        string="Attendance Approver",
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
        groups="hr_attendance.group_hr_attendance_officer,hr_attendance.group_hr_attendance_own_reader",
        help="The user set in Attendance will access the attendance of the employee through the dedicated app and will be able to edit them.")
    attendance_ids = fields.One2many(
        'hr.attendance', 'employee_id', groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user")
    last_attendance_id = fields.Many2one(
        'hr.attendance', compute='_compute_last_attendance_id', store=True,
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user")
    last_check_in = fields.Datetime(
        related='last_attendance_id.check_in', store=True,
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user", tracking=False)
    last_check_out = fields.Datetime(
        related='last_attendance_id.check_out', store=True,
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user", tracking=False)
    attendance_state = fields.Selection(
        string="Attendance Status", compute='_compute_attendance_state',
        selection=[('checked_out', "Checked out"), ('checked_in', "Checked in")],
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user")
    hours_last_month = fields.Float(compute='_compute_hours_last_month')
    hours_last_month_overtime = fields.Float(compute='_compute_hours_last_month')
    hours_today = fields.Float(
        compute='_compute_hours_today',
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user")
    hours_previously_today = fields.Float(
        compute='_compute_hours_today',
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user")
    last_attendance_worked_hours = fields.Float(
        compute='_compute_hours_today',
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user")
    hours_last_month_display = fields.Char(
        compute='_compute_hours_last_month', groups="hr.group_hr_user")
    overtime_ids = fields.One2many(
        'hr.attendance.overtime.line', 'employee_id', groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user")
    total_overtime = fields.Float(compute='_compute_total_overtime', compute_sudo=True)
    display_extra_hours = fields.Boolean(related='company_id.hr_attendance_display_overtime')

    # Hours Balance fields
    hours_balance = fields.Float(
        string='Hours Balance',
        compute='_compute_hours_balance',
        compute_sudo=True,
        store=False,  # Don't store, compute on-demand
        help='Cumulative hours balance (overtime minus undertime), including manual adjustments. Positive means extra hours worked, negative means hours owed.')
    hours_balance_start_date = fields.Date(
        string='Balance Start Date',
        help='Date from which to start calculating hours balance. Defaults to employee creation or 1 year ago.')

    ignore_negative_expected_hours = fields.Boolean(
        string='Nie licz ujemnych godzin',
        help='Jeśli zaznaczone, system nie będzie naliczał ujemnego salda za przepracowanie mniejszej liczby godzin niż oczekiwana.'
    )

    # Manual adjustment fields
    hours_balance_adjustment_ids = fields.One2many(
        'hr.hours.balance.adjustment',
        'employee_id',
        string='Balance Adjustments',
        help='Manual adjustments applied to hours balance')
    hours_balance_adjustment_count = fields.Integer(
        string='Adjustment Count',
        compute='_compute_hours_balance_adjustment_count')

    ruleset_id = fields.Many2one(readonly=False, related="version_id.ruleset_id", inherited=True, groups="hr.group_hr_manager")

    @api.depends('hours_balance_adjustment_ids')
    def _compute_hours_balance_adjustment_count(self):
        for employee in self:
            employee.hours_balance_adjustment_count = len(employee.hours_balance_adjustment_ids)

    @api.model_create_multi
    def create(self, vals_list):
        officer_group = self.env.ref('hr_attendance.group_hr_attendance_officer', raise_if_not_found=False)
        group_updates = []
        for vals in vals_list:
            if officer_group and vals.get('attendance_manager_id'):
                group_updates.append((4, vals['attendance_manager_id']))
        if group_updates:
            officer_group.sudo().write({'user_ids': group_updates})
        return super().create(vals_list)

    def write(self, vals):
        old_officers = self.env['res.users']
        if 'attendance_manager_id' in vals:
            old_officers = self.attendance_manager_id
            # Officer was added
            if vals['attendance_manager_id']:
                officer = self.env['res.users'].browse(vals['attendance_manager_id'])
                officers_group = self.env.ref('hr_attendance.group_hr_attendance_officer', raise_if_not_found=False)
                if officers_group and not officer.has_group('hr_attendance.group_hr_attendance_officer'):
                    officer.sudo().write({'group_ids': [(4, officers_group.id)]})

        res = super().write(vals)
        old_officers.sudo()._clean_attendance_officers()

        return res

    @api.depends('overtime_ids.manual_duration', 'overtime_ids', 'overtime_ids.status')
    def _compute_total_overtime(self):
        mapped_validated_overtimes = dict(
            self.env['hr.attendance.overtime.line']._read_group(
            domain=[('status', '=', 'approved')],
            groupby=['employee_id'],
            aggregates=['manual_duration:sum']
        ))

        for employee in self:
            employee.total_overtime = mapped_validated_overtimes.get(employee, 0)

    def _compute_hours_last_month(self):
        """
        Compute hours and overtime hours in the current month, if we are the 15th of october, will compute from 1 oct to 15 oct
        """
        now = fields.Datetime.now()
        now_utc = pytz.utc.localize(now)
        for employee in self:
            tz = pytz.timezone(employee.tz or 'UTC')
            now_tz = now_utc.astimezone(tz)
            start_tz = now_tz.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_naive = start_tz.astimezone(pytz.utc).replace(tzinfo=None)
            end_tz = now_tz
            end_naive = end_tz.astimezone(pytz.utc).replace(tzinfo=None)

            current_month_attendances = employee.attendance_ids.filtered(
                lambda att: att.check_in >= start_naive and att.check_out and att.check_out <= end_naive
            )
            hours = 0
            overtime_hours = 0
            for att in current_month_attendances:
                hours += att.worked_hours or 0
                overtime_hours += att.validated_overtime_hours or 0
            employee.hours_last_month = round(hours, 2)
            employee.hours_last_month_display = "%g" % employee.hours_last_month
            # overtime_adjustments = sum(
            #     ot.duration or 0
            #     for ot in employee.overtime_ids.filtered(
            #         lambda ot: ot.date >= start_tz.date() and ot.date <= end_tz.date() and ot.adjustment
            #     )
            # )
            employee.hours_last_month_overtime = round(overtime_hours, 2)

    def _compute_hours_today(self):
        now = fields.Datetime.now()
        now_utc = pytz.utc.localize(now)
        for employee in self:
            # start of day in the employee's timezone might be the previous day in utc
            tz = pytz.timezone(employee.tz)
            now_tz = now_utc.astimezone(tz)
            start_tz = now_tz + relativedelta(hour=0, minute=0)  # day start in the employee's timezone
            start_naive = start_tz.astimezone(pytz.utc).replace(tzinfo=None)

            attendances = self.env['hr.attendance'].search([
                ('employee_id', 'in', employee.ids),
                ('check_in', '<=', now),
                '|', ('check_out', '>=', start_naive), ('check_out', '=', False),
            ], order='check_in asc')
            hours_previously_today = 0
            worked_hours = 0
            attendance_worked_hours = 0
            for attendance in attendances:
                delta = (attendance.check_out or now) - max(attendance.check_in, start_naive)
                attendance_worked_hours = delta.total_seconds() / 3600.0
                worked_hours += attendance_worked_hours
                hours_previously_today += attendance_worked_hours
            employee.last_attendance_worked_hours = attendance_worked_hours
            hours_previously_today -= attendance_worked_hours
            employee.hours_previously_today = hours_previously_today
            employee.hours_today = worked_hours

    @api.depends('attendance_ids')
    def _compute_last_attendance_id(self):
        for employee in self:
            employee.last_attendance_id = self.env['hr.attendance'].search([
                ('employee_id', 'in', employee.ids),
            ], order="check_in desc", limit=1)

    @api.depends('last_attendance_id.check_in', 'last_attendance_id.check_out', 'last_attendance_id')
    def _compute_attendance_state(self):
        for employee in self:
            att = employee.last_attendance_id.sudo()
            employee.attendance_state = att and not att.check_out and 'checked_in' or 'checked_out'

    def _attendance_action_change(self, geo_information=None):
        """ Check In/Check Out action
            Check In: create a new attendance record
            Check Out: modify check_out field of appropriate attendance record

        PERFORMANCE OPTIMIZATION: Derives attendance state from stored last_attendance_id
        field instead of accessing the computed attendance_state field, which would trigger
        expensive database searches after ORM cache invalidation (e.g., after kiosk inactivity).
        """
        self.ensure_one()
        action_date = fields.Datetime.now()

        # Derive state from STORED last_attendance_id field instead of computed attendance_state
        last_att = self.last_attendance_id
        is_checked_in = bool(last_att and not last_att.check_out)

        if not is_checked_in:
            if geo_information:
                vals = {
                    'employee_id': self.id,
                    'check_in': action_date,
                    **{'in_%s' % key: geo_information[key] for key in geo_information}
                }
            else:
                vals = {
                    'employee_id': self.id,
                    'check_in': action_date,
                }
            return self.env['hr.attendance'].create(vals)
        attendance = self.env['hr.attendance'].search([('employee_id', '=', self.id), ('check_out', '=', False)], limit=1)
        if attendance:
            if geo_information:
                attendance.write({
                    'check_out': action_date,
                    **{'out_%s' % key: geo_information[key] for key in geo_information}
                })
            else:
                attendance.write({
                    'check_out': action_date
                })
        else:
            raise exceptions.UserError(_(
                'Cannot perform check out on %(empl_name)s, could not find corresponding check in. '
                'Your attendances have probably been modified manually by human resources.',
                empl_name=self.sudo().name))
        return attendance

    @api.model
    def get_overtime_data(self, domain=None, employee_id=None):
        domain = [] if domain is None else domain
        validated_overtime = {
            attendance[0].id: attendance[1]
            for attendance in self.env["hr.attendance"]._read_group(
                domain=domain,
                groupby=['employee_id'],
                aggregates=['validated_overtime_hours:sum']
            )
        }
        return {"validated_overtime": validated_overtime, "overtime_adjustments": {}}

    def action_open_last_month_attendances(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Attendances This Month"),
            "res_model": "hr.attendance",
            "views": [[self.env.ref('hr_attendance.hr_attendance_employee_simple_tree_view').id, "list"]],
            "context": {
                "create": 0,
                "search_default_check_in_filter": 1,
                "employee_id": self.id,
                "display_extra_hours": self.display_extra_hours,
            },
            "domain": [('employee_id', '=', self.id)]
        }

    @api.depends("user_id.im_status", "attendance_state")
    def _compute_presence_state(self):
        """
        Override to include checkin/checkout in the presence state
        Attendance has the second highest priority after login
        """
        super()._compute_presence_state()
        employees = self.filtered(lambda e: e.hr_presence_state != "present")
        employee_to_check_working = self.filtered(lambda e: e.sudo().attendance_state == "checked_out"
                                                            and e.hr_presence_state == "out_of_working_hour")
        working_now_list = employee_to_check_working._get_employee_working_now()
        for employee in employees:
            if employee.sudo().attendance_state == "checked_out" and employee.hr_presence_state == "out_of_working_hour" and \
                    employee.id in working_now_list:
                employee.hr_presence_state = "absent"
            elif employee.sudo().attendance_state == "checked_in":
                employee.hr_presence_state = "present"

    def _compute_presence_icon(self):
        res = super()._compute_presence_icon()
        # All employee must chek in or check out. Everybody must have an icon
        for employee in self:
            employee.show_hr_icon_display = employee.company_id.hr_presence_control_attendance or bool(employee.user_id)
        return res

    def open_barcode_scanner(self):
        return {
            "type": "ir.actions.client",
            "tag": "employee_barcode_scanner",
            "name": "Badge Scanner"
        }

    def _compute_hours_balance(self):
        """
        Compute cumulative hours balance for each employee, including manual adjustments.
        Formula: (worked hours - expected hours) + manual adjustments
        """
        for employee in self:
            # Get calculated balance (worked - expected)
            calculated_balance = employee._compute_hours_balance_value()

            # Add manual adjustments
            total_adjustments = sum(
                employee.hours_balance_adjustment_ids.mapped('adjustment_amount')
            )

            employee.hours_balance = _round_half_hour(calculated_balance + total_adjustments)

    def _compute_hours_balance_value(self):
        """
        Calculate hours balance WITHOUT manual adjustments.
        Used for both display and as baseline for adjustments.
        Returns: float (hours balance)

        Calculates: total worked hours - total expected hours
        Weekend work counts as pure bonus (no expected hours)
        Counts absent workdays as negative balance
        """
        from datetime import datetime, timedelta
        from collections import defaultdict

        self.ensure_one()

        if not self.id:
            return 0.0

        # Get start date for calculation
        if self.hours_balance_start_date:
            start_date = self.hours_balance_start_date
        else:
            # Find first attendance check-in date
            first_attendance = self.env['hr.attendance'].search([
                ('employee_id', '=', self.id),
                ('check_in', '!=', False)
            ], order='check_in asc', limit=1)

            if first_attendance:
                start_date = first_attendance.check_in.date()
            else:
                # No attendance records, balance will be 0
                return 0.0

        # End date is yesterday (exclude current day since work isn't finished)
        end_date = datetime.now().date() - timedelta(days=1)

        # Get timezone
        tz = pytz.timezone(self.tz or 'UTC')

        # Get resource calendar
        calendar = self.resource_calendar_id or self.company_id.resource_calendar_id

        # Fetch all attendances for the period
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())

        attendances = self.env['hr.attendance'].search([
            ('employee_id', '=', self.id),
            ('check_in', '>=', start_datetime),
            ('check_in', '<=', end_datetime),
            ('check_out', '!=', False),
        ])

        # Group attendances by date
        worked_by_date = defaultdict(float)
        for att in attendances:
            att_date = att.check_in.date()
            worked_by_date[att_date] += att.worked_hours

        # Fetch all leaves for the period
        leaves = self.env['hr.leave'].search([
            ('employee_id', '=', self.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', fields.Datetime.to_datetime(end_date)),
            ('date_to', '>=', fields.Datetime.to_datetime(start_date)),
        ])

        # Build set of dates with approved leaves
        leave_dates = set()
        for leave in leaves:
            leave_start = leave.date_from.date() if isinstance(leave.date_from, datetime) else leave.date_from
            leave_end = leave.date_to.date() if isinstance(leave.date_to, datetime) else leave.date_to
            current = leave_start
            while current <= leave_end:
                if current >= start_date and current <= end_date:
                    leave_dates.add(current)
                current += timedelta(days=1)

        # Calculate balance for each day from start to end
        balance = 0.0
        current_date = start_date

        while current_date <= end_date:
            weekday = current_date.weekday()
            is_weekend = weekday >= 5  # Saturday=5, Sunday=6

            # Check for public holiday
            datetime_start = datetime.combine(current_date, datetime.min.time())
            datetime_end = datetime.combine(current_date, datetime.max.time())
            datetime_start_utc = tz.localize(datetime_start).astimezone(pytz.utc)
            datetime_end_utc = tz.localize(datetime_end).astimezone(pytz.utc)
            datetime_start_naive = datetime_start_utc.replace(tzinfo=None)
            datetime_end_naive = datetime_end_utc.replace(tzinfo=None)

            # Check for public holidays (global calendar leaves only, not individual employee leaves)
            public_holiday = self.env['resource.calendar.leaves'].search([
                ('calendar_id', '=', calendar.id),
                ('date_from', '<=', datetime_end_naive),
                ('date_to', '>=', datetime_start_naive),
                ('resource_id', '=', False)  # Only global public holidays, not individual leaves
            ], limit=1)
            is_public_holiday = bool(public_holiday)

            # Check for approved leave
            has_approved_leave = current_date in leave_dates

            # Get expected hours
            # if is_public_holiday or has_approved_leave or is_weekend:
            #     expected_hours = 0.0
            # else:
            #     # Get work intervals for this day
            #     work_intervals = calendar._work_intervals_batch(
            #         datetime_start_utc, datetime_end_utc,
            #         resources=self.resource_id
            #     )[self.resource_id.id]
            #     expected_hours = sum(
            #         (stop - start).total_seconds() / 3600.0
            #         for start, stop, meta in work_intervals
            #     )
            if is_public_holiday or has_approved_leave or is_weekend:
                expected_hours = 0.0
            else:
                expected_hours = 8.0
            # Get actual worked hours
            worked_hours = worked_by_date.get(current_date, 0.0)

            # Calculate balance delta
            if is_public_holiday or has_approved_leave or is_weekend:
                # Public holidays, approved leaves, and weekends: all worked hours count as bonus
                # If no work, no penalty (balance_delta = 0)
                balance_delta = worked_hours
            else:
                # Regular weekday: difference between worked and expected
                balance_delta = worked_hours - expected_hours

                # For selected employees, do not count negative expected-hours balance
                if self.ignore_negative_expected_hours and balance_delta < 0:
                    balance_delta = 0.0

            # Round daily delta to nearest 0.5h (15-min threshold)
            balance_delta = _round_half_hour(balance_delta)
            balance += balance_delta
            current_date += timedelta(days=1)

        return balance

    def action_view_hours_balance_detail(self):
        """
        Open detailed view of hours balance breakdown by day.
        Shows how the balance was calculated with daily +/- entries.
        """
        self.ensure_one()

        # Determine date range (from balance start or first attendance to yesterday)
        from datetime import datetime, timedelta
        end_date = datetime.now().date() - timedelta(days=1)

        if self.hours_balance_start_date:
            start_date = self.hours_balance_start_date
        else:
            # Find first attendance check-in date
            first_attendance = self.env['hr.attendance'].search([
                ('employee_id', '=', self.id),
                ('check_in', '!=', False)
            ], order='check_in asc', limit=1)

            if first_attendance:
                start_date = first_attendance.check_in.date()
            else:
                # No attendance records, show last 30 days
                start_date = end_date - timedelta(days=30)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Hours Balance Detail: %s') % self.name,
            'res_model': 'hr.employee.hours.balance.line',
            'views': [[False, 'list'], [False, 'graph']],
            'view_mode': 'list,graph',
            'target': 'current',
            'domain': [
                ('employee_id', '=', self.id),
                ('date', '>=', start_date),
                ('date', '<=', end_date),
            ],
            'context': {
                'default_employee_id': self.id,
                'group_by': ['month'],
                'create': False,  # Disable create button
                'edit': False,    # Disable edit
                'delete': False,  # Disable delete
            },
            'flags': {
                'mode': 'readonly',  # Read-only mode
            },
        }

    def action_adjust_hours_balance(self):
        """Open wizard to adjust hours balance"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Adjust Hours Balance',
            'res_model': 'hr.hours.balance.adjustment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_employee_id': self.id,
            }
        }

    def action_view_balance_adjustments(self):
        """View all balance adjustments for this employee"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Balance Adjustments - {self.name}',
            'res_model': 'hr.hours.balance.adjustment',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id}
        }
