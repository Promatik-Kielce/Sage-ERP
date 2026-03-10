# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta
from collections import defaultdict
import pytz

from odoo import models, fields, api, _
from odoo.addons.hr_attendance.models.hr_employee import _round_half_hour


class HrEmployeeHoursBalanceLine(models.Model):
    """
    Daily breakdown of employee hours balance.
    This is a computed model (no database storage) that shows day-by-day
    how the hours balance is calculated.
    """
    _name = 'hr.employee.hours.balance.line'
    _description = 'Employee Hours Balance Line'
    _order = 'date desc, employee_id'
    _auto = False  # This is a compute-only model, no table created

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    date = fields.Date(string='Date', required=True)
    day_of_week = fields.Char(string='Day')
    check_in_time = fields.Char(string='Wejście')
    check_out_time = fields.Char(string='Wyjście')
    worked_hours = fields.Float(string='Worked Hours')
    expected_hours = fields.Float(string='Expected Hours')
    is_weekend = fields.Boolean(string='Weekend')
    is_public_holiday = fields.Boolean(string='Public Holiday')
    has_approved_leave = fields.Boolean(string='Has Leave')
    leave_name = fields.Char(string='Leave Type')
    output_balance_minutes = fields.Integer(string='Output Balance Minutes')
    output_balance = fields.Char(string='Output Balance')
    output_balance_type = fields.Selection(
        [
            ('early', 'Early'),
            ('late', 'Late'),
            ('on_time', 'On Time'),
        ],
        string='Output Balance Type'
    )
    balance_delta = fields.Float(string='Daily +/-', help='Change in balance for this day')
    balance_cumulative = fields.Float(string='Total Balance', help='Running total balance up to this date')
    notes = fields.Text(string='Calculation Notes')
    attendance_count = fields.Integer(string='# Attendances')
    month = fields.Char(string='Month', search='_search_month')

    # Split fields for chart coloring
    balance_delta_positive = fields.Float(string='Daily + (Surplus)', compute='_compute_split_values', store=False, group_operator='sum')
    balance_delta_negative = fields.Float(string='Daily - (Deficit)', compute='_compute_split_values', store=False, group_operator='sum')
    balance_cumulative_positive = fields.Float(string='Balance + (Surplus)', compute='_compute_split_values', store=False, group_operator='sum')
    balance_cumulative_negative = fields.Float(string='Balance - (Deficit)', compute='_compute_split_values', store=False, group_operator='sum')

    def _get_polish_day_name(self, date_value):
        day_names = {
            0: 'Poniedziałek',
            1: 'Wtorek',
            2: 'Środa',
            3: 'Czwartek',
            4: 'Piątek',
            5: 'Sobota',
            6: 'Niedziela',
        }
        return day_names.get(date_value.weekday(), '')

    def _format_time_for_employee_tz(self, dt_value, tz):
        if not dt_value:
            return ''
        if dt_value.tzinfo is None:
            dt_value = pytz.utc.localize(dt_value)
        return dt_value.astimezone(tz).strftime('%H:%M')

    def _format_minutes_to_hhmm(self, minutes):
        sign = '-' if minutes < 0 else ''
        abs_minutes = abs(int(minutes))
        hours = abs_minutes // 60
        mins = abs_minutes % 60
        return f'{sign}{hours:02d}:{mins:02d}'

    def _format_hours_to_hhmm(self, hours_value, signed=False):
        """
        Convert decimal hours to HH:MM format.
        Example:
            8.23 -> 08:14
            0.27 -> 00:16
            -0.27 -> -00:16
        """
        if hours_value is None:
            return ''

        total_minutes = int(round(hours_value * 60))
        sign = ''

        if signed and total_minutes > 0:
            sign = '+'
        elif total_minutes < 0:
            sign = '-'

        abs_minutes = abs(total_minutes)
        hours = abs_minutes // 60
        minutes = abs_minutes % 60
        return f'{sign}{hours:02d}:{minutes:02d}'

    @api.depends('balance_delta', 'balance_cumulative')
    def _compute_split_values(self):
        """Split positive and negative values for chart coloring"""
        for line in self:
            # Split daily balance
            if line.balance_delta >= 0:
                line.balance_delta_positive = line.balance_delta
                line.balance_delta_negative = 0.0
            else:
                line.balance_delta_positive = 0.0
                line.balance_delta_negative = abs(line.balance_delta)  # Store as positive for display

            # Split cumulative balance
            if line.balance_cumulative >= 0:
                line.balance_cumulative_positive = line.balance_cumulative
                line.balance_cumulative_negative = 0.0
            else:
                line.balance_cumulative_positive = 0.0
                line.balance_cumulative_negative = abs(line.balance_cumulative)  # Store as positive for display

    def _search_month(self, operator, value):
        """Dummy search method to pass view validation. Actual filtering is in search_read."""
        return []

    @api.model
    def _get_balance_lines_for_employee(self, employee, start_date=None, end_date=None):
        """
        Generate balance lines for an employee for the specified date range.

        This is the core calculation logic that:
        1. Gets expected hours from resource calendar
        2. Gets worked hours from attendance records
        3. Checks for weekends, holidays, and leaves
        4. Calculates daily delta and cumulative balance

        Returns: list of dicts with balance line data
        """
        if not start_date:
            # Default to employee's balance start date, or first attendance date
            if employee.hours_balance_start_date:
                start_date = employee.hours_balance_start_date
            else:
                # Find first attendance check-in date
                first_attendance = self.env['hr.attendance'].search([
                    ('employee_id', '=', employee.id),
                    ('check_in', '!=', False)
                ], order='check_in asc', limit=1)

                if first_attendance:
                    start_date = first_attendance.check_in.date()
                else:
                    # No attendance records, start from today (will show no data)
                    start_date = datetime.now().date()

        if not end_date:
            # Exclude current day since work isn't finished yet
            end_date = datetime.now().date() - timedelta(days=1)

        # Include today for adjustments (they can be created with today's date)
        adjustments_end_date = datetime.now().date()

        # Get employee timezone
        tz = pytz.timezone(employee.tz or 'UTC')

        # Get resource calendar
        calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id

        # Fetch all attendances for the period
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())

        attendances = self.env['hr.attendance'].search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', start_datetime),
            ('check_in', '<=', end_datetime),
            ('check_out', '!=', False),
        ])

        # Group attendances by date (using check_in date)
        attendance_by_date = defaultdict(list)
        for att in attendances:
            att_date = pytz.utc.localize(att.check_in).astimezone(tz).date() if att.check_in.tzinfo is None else att.check_in.astimezone(tz).date()
            attendance_by_date[att_date].append(att)

        # Fetch all leaves for the period
        leaves = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', fields.Datetime.to_datetime(end_date)),
            ('date_to', '>=', fields.Datetime.to_datetime(start_date)),
        ])

        # Build set of dates with approved leaves
        leave_dates = {}
        for leave in leaves:
            leave_start = leave.date_from.date() if isinstance(leave.date_from, datetime) else leave.date_from
            leave_end = leave.date_to.date() if isinstance(leave.date_to, datetime) else leave.date_to
            current = leave_start
            while current <= leave_end:
                if current >= start_date and current <= end_date:
                    leave_dates[current] = leave.holiday_status_id.name
                current += timedelta(days=1)

        # Fetch all manual balance adjustments for the period (including today)
        adjustments = self.env['hr.hours.balance.adjustment'].search([
            ('employee_id', '=', employee.id),
            ('date', '>=', start_date),
            ('date', '<=', adjustments_end_date),
        ], order='date asc, id asc')

        # Group adjustments by date
        adjustments_by_date = defaultdict(list)
        for adj in adjustments:
            adjustments_by_date[adj.date].append(adj)

        # Calculate initial balance directly without recursion
        # This prevents double-counting or missing adjustments

        # 1. Sum all adjustments before start_date
        prior_adjustments = self.env['hr.hours.balance.adjustment'].search([
            ('employee_id', '=', employee.id),
            ('date', '<', start_date),
        ])
        initial_adjustment_balance = sum(prior_adjustments.mapped('adjustment_amount'))

        # 2. Calculate work balance (worked - expected) before start_date
        initial_work_balance = 0.0
        if employee.hours_balance_start_date and employee.hours_balance_start_date < start_date:
            # Calculate by iterating through each prior date
            prior_start = employee.hours_balance_start_date
            prior_end = start_date - timedelta(days=1)

            # Fetch prior attendances
            prior_attendances = self.env['hr.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', datetime.combine(prior_start, datetime.min.time())),
                ('check_in', '<=', datetime.combine(prior_end, datetime.max.time())),
                ('check_out', '!=', False),
            ])

            # Group by date
            prior_attendance_by_date = defaultdict(list)
            for att in prior_attendances:
                att_date = pytz.utc.localize(att.check_in).astimezone(tz).date() if att.check_in.tzinfo is None else att.check_in.astimezone(tz).date()
                prior_attendance_by_date[att_date].append(att)

            # Calculate balance for each prior date
            prior_date = prior_start
            while prior_date <= prior_end:
                # Get expected hours
                weekday = prior_date.weekday()
                is_weekend = weekday >= 5

                # if is_weekend:
                #     expected_hours = 0.0
                # else:
                #     # Calculate expected hours for this date
                #     datetime_start = datetime.combine(prior_date, datetime.min.time())
                #     datetime_end = datetime.combine(prior_date, datetime.max.time())
                #     datetime_start_utc = tz.localize(datetime_start).astimezone(pytz.utc)
                #     datetime_end_utc = tz.localize(datetime_end).astimezone(pytz.utc)
                #
                #     work_intervals = calendar._work_intervals_batch(
                #         datetime_start_utc, datetime_end_utc,
                #         resources=employee.resource_id
                #     )[employee.resource_id.id]
                #     expected_hours = sum(
                #         (stop - start).total_seconds() / 3600.0
                #         for start, stop, meta in work_intervals
                #     )
                if is_weekend:
                    expected_hours = 0.0
                else:
                    expected_hours = 8.0
                # Get worked hours
                day_attendances = prior_attendance_by_date.get(prior_date, [])
                worked_hours = sum(att.worked_hours for att in day_attendances)

                # Add to balance (simplified - using basic worked - expected)
                prior_delta = worked_hours - expected_hours
                if employee.ignore_negative_expected_hours and prior_delta < 0:
                    prior_delta = 0.0
                initial_work_balance += _round_half_hour(prior_delta)

                prior_date += timedelta(days=1)

        initial_balance = initial_work_balance + initial_adjustment_balance

        # Calculate balance for each day
        balance_lines = []
        cumulative_balance = initial_balance

        current_date = start_date
        while current_date <= end_date:
            # Get day of week (0=Monday, 6=Sunday)
            weekday = current_date.weekday()
            is_weekend = weekday >= 5  # Saturday=5, Sunday=6

            # Check for public holiday using resource calendar
            datetime_start = datetime.combine(current_date, datetime.min.time())
            datetime_end = datetime.combine(current_date, datetime.max.time())
            datetime_start_utc = tz.localize(datetime_start).astimezone(pytz.utc)
            datetime_end_utc = tz.localize(datetime_end).astimezone(pytz.utc)

            # Check if this date has a public holiday (resource.calendar.leaves)
            # Note: calendar.leaves dates are stored without timezone in DB
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
            leave_name = leave_dates.get(current_date, '')

            # Get expected hours from calendar for this day
            # if is_public_holiday or has_approved_leave or is_weekend:
            #     expected_hours = 0.0
            # else:
            #     # Get work intervals for this day (requires timezone-aware datetimes)
            #     work_intervals = calendar._work_intervals_batch(
            #         datetime_start_utc, datetime_end_utc,
            #         resources=employee.resource_id
            #     )[employee.resource_id.id]
            #     expected_hours = sum(
            #         (stop - start).total_seconds() / 3600.0
            #         for start, stop, meta in work_intervals
            #     )
            if is_public_holiday or has_approved_leave or is_weekend:
                expected_hours = 0.0
            else:
                expected_hours = 8.0
            # Get actual worked hours
            day_attendances = attendance_by_date.get(current_date, [])
            worked_hours = sum(att.worked_hours for att in day_attendances)
            attendance_count = len(day_attendances)

            # Pola Wejcia i Wyjcia
            day_of_week = self._get_polish_day_name(current_date)

            valid_check_ins = [att.check_in for att in day_attendances if att.check_in]
            valid_check_outs = [att.check_out for att in day_attendances if att.check_out]

            first_check_in = min(valid_check_ins) if valid_check_ins else False
            last_check_out = max(valid_check_outs) if valid_check_outs else False

            check_in_time = self._format_time_for_employee_tz(first_check_in, tz) if first_check_in else ''
            check_out_time = self._format_time_for_employee_tz(last_check_out, tz) if last_check_out else ''

            output_balance_minutes = 0
            output_balance = ''
            output_balance_type = 'on_time'

            if (
                    first_check_in and
                    last_check_out and
                    expected_hours > 0 and
                    not is_weekend and
                    not is_public_holiday and
                    not has_approved_leave
            ):
                planned_end = first_check_in + timedelta(hours=expected_hours)
                delta_seconds = (last_check_out - planned_end).total_seconds()
                output_balance_minutes = int(round(delta_seconds / 60.0))

                if employee.ignore_negative_expected_hours and output_balance_minutes < 0:
                    output_balance_minutes = 0

                output_balance = self._format_minutes_to_hhmm(output_balance_minutes)

                if output_balance_minutes < 0:
                    output_balance_type = 'early'
                elif output_balance_minutes > 0:
                    output_balance_type = 'late'
                else:
                    output_balance_type = 'on_time'


            # Check if any attendance is technical (absence detection)
            has_technical_attendance = any(att.in_mode == 'technical' for att in day_attendances)

            # Calculate balance delta based on rules
            if is_public_holiday:
                # Public holidays: worked hours count as bonus
                balance_delta = worked_hours
                if worked_hours > 0:
                    notes = _('Praca w święto: bonus %s') % self._format_hours_to_hhmm(worked_hours, signed=True)
                else:
                    notes = _('Święto - brak oczekiwanej pracy')
            elif has_approved_leave:
                # Approved leave: worked hours count as bonus
                balance_delta = worked_hours
                if worked_hours > 0:
                    notes = _('Praca podczas urlopu (%s): bonus %s') % (
                        leave_name,
                        self._format_hours_to_hhmm(worked_hours, signed=True)
                    )
                else:
                    notes = _('Zatwierdzony urlop: %s') % leave_name
            elif is_weekend:
                # Weekend: all worked hours are bonus
                balance_delta = worked_hours
                if worked_hours > 0:
                    notes = _('Praca w weekend: bonus %s') % self._format_hours_to_hhmm(worked_hours, signed=True)
                else:
                    notes = _('Weekend - brak oczekiwanej pracy')
            else:
                # Weekday (Mon-Fri): difference between worked and expected
                raw_balance_delta = worked_hours - expected_hours
                balance_delta = raw_balance_delta

                if employee.ignore_negative_expected_hours and balance_delta < 0:
                    balance_delta = 0.0

                    if attendance_count == 0 and expected_hours > 0:
                        notes = _('Brak obecności, ale ujemne godziny są pomijane dla tego pracownika')
                    elif has_technical_attendance:
                        notes = _(
                            'Nieobecność wykryta przez system, ale ujemne godziny są pomijane dla tego pracownika')
                    elif worked_hours > 0:
                        notes = _('Przepracowano %s, oczekiwano %s: ujemne godziny pominięto') % (
                            self._format_hours_to_hhmm(worked_hours),
                            self._format_hours_to_hhmm(expected_hours),
                        )
                    else:
                        notes = _('Ujemne godziny pominięto dla tego pracownika')
                else:
                    if attendance_count == 0 and expected_hours > 0:
                        notes = _('Nieobecność: %s (brak zarejestrowanej obecności)') % (
                            self._format_hours_to_hhmm(-expected_hours)
                        )
                    elif has_technical_attendance:
                        notes = _('Nieobecność: %s (nieobecność wykryta przez system)') % (
                            self._format_hours_to_hhmm(-expected_hours)
                        )
                    elif worked_hours >= expected_hours:
                        overtime = worked_hours - expected_hours
                        notes = _('Przepracowano %s, oczekiwano %s: nadgodziny %s') % (
                            self._format_hours_to_hhmm(worked_hours),
                            self._format_hours_to_hhmm(expected_hours),
                            self._format_hours_to_hhmm(overtime, signed=True)
                        )
                    else:
                        undertime = expected_hours - worked_hours
                        notes = _('Przepracowano %s, oczekiwano %s: niedoczas %s') % (
                            self._format_hours_to_hhmm(worked_hours),
                            self._format_hours_to_hhmm(expected_hours),
                            self._format_hours_to_hhmm(-undertime)
                        )

            # Round daily delta to nearest 0.5h (15-min threshold)
            raw_delta = balance_delta
            balance_delta = _round_half_hour(balance_delta)
            if round(raw_delta, 2) != round(balance_delta, 2):
                notes += _(' [zaokrąglono %s → %s]') % (
                    self._format_hours_to_hhmm(raw_delta, signed=True),
                    self._format_hours_to_hhmm(balance_delta, signed=True),
                )

            cumulative_balance += balance_delta

            balance_lines.append({
                'employee_id': employee.id,
                'date': current_date,
                'day_of_week': day_of_week,
                'check_in_time': check_in_time,
                'check_out_time': check_out_time,
                'month': current_date.strftime('%Y-%m'),
                'worked_hours': worked_hours,
                'expected_hours': expected_hours,
                'is_weekend': is_weekend,
                'is_public_holiday': is_public_holiday,
                'has_approved_leave': has_approved_leave,
                'leave_name': leave_name,
                'balance_delta': balance_delta,
                'output_balance_minutes': output_balance_minutes,
                'output_balance': output_balance,
                'output_balance_type': output_balance_type,
                'balance_cumulative': cumulative_balance,
                'notes': notes,
                'attendance_count': attendance_count,
            })

            # Add any manual adjustments for this date
            if current_date in adjustments_by_date:
                for adjustment in adjustments_by_date[current_date]:
                    rounded_adj = _round_half_hour(adjustment.adjustment_amount)
                    cumulative_balance += rounded_adj

                    # Create adjustment entry
                    adjustment_notes = _('✏️ Korekta ręczna: %s\nPowód: %s\nWprowadził: %s') % (
                        self._format_hours_to_hhmm(adjustment.adjustment_amount, signed=True),
                        adjustment.reason,
                        adjustment.user_id.name
                    )
                    if round(adjustment.adjustment_amount, 2) != round(rounded_adj, 2):
                        adjustment_notes += _(' [zaokrąglono %s → %s]') % (
                            self._format_hours_to_hhmm(adjustment.adjustment_amount, signed=True),
                            self._format_hours_to_hhmm(rounded_adj, signed=True),
                        )

                    balance_lines.append({
                        'employee_id': employee.id,
                        'date': current_date,
                        'day_of_week': day_of_week,
                        'check_in_time': '',
                        'check_out_time': '',
                        'month': current_date.strftime('%Y-%m'),
                        'worked_hours': 0.0,  # Adjustments don't have worked hours
                        'expected_hours': 0.0,
                        'is_weekend': is_weekend,
                        'is_public_holiday': False,
                        'has_approved_leave': False,
                        'leave_name': '',
                        'balance_delta': rounded_adj,
                        'output_balance_minutes': 0,
                        'output_balance': '',
                        'output_balance_type': 'on_time',
                        'balance_cumulative': cumulative_balance,
                        'notes': adjustment_notes,
                        'attendance_count': 0,
                    })

            current_date += timedelta(days=1)

        # Add adjustments dated after end_date (e.g., today's adjustments)
        # These are included in the widget balance but need to be shown in detail view too
        for adj_date in sorted(adjustments_by_date.keys()):
            if adj_date > end_date:
                for adjustment in adjustments_by_date[adj_date]:
                    rounded_adj = _round_half_hour(adjustment.adjustment_amount)
                    cumulative_balance += rounded_adj

                    adjustment_notes = _('✏️ Manual Adjustment: %s%s hours\nReason: %s\nAdjusted by: %s') % (
                        '+' if adjustment.adjustment_amount > 0 else '',
                        round(adjustment.adjustment_amount, 2),
                        adjustment.reason,
                        adjustment.user_id.name
                    )
                    if round(adjustment.adjustment_amount, 2) != round(rounded_adj, 2):
                        adjustment_notes += _(' [rounded %s%sh → %s%sh]') % (
                            '+' if adjustment.adjustment_amount >= 0 else '', round(adjustment.adjustment_amount, 2),
                            '+' if rounded_adj >= 0 else '', round(rounded_adj, 2),
                        )

                    balance_lines.append({
                        'employee_id': employee.id,
                        'date': adj_date,
                        'day_of_week': self._get_polish_day_name(adj_date),
                        'check_in_time': '',
                        'check_out_time': '',
                        'month': adj_date.strftime('%Y-%m'),
                        'worked_hours': 0.0,
                        'expected_hours': 0.0,
                        'is_weekend': adj_date.weekday() >= 5,
                        'is_public_holiday': False,
                        'has_approved_leave': False,
                        'leave_name': '',
                        'balance_delta': rounded_adj,
                        'output_balance_minutes': 0,
                        'output_balance': '',
                        'output_balance_type': 'on_time',
                        'balance_cumulative': cumulative_balance,
                        'notes': adjustment_notes,
                        'attendance_count': 0,
                    })

        return balance_lines

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """
        Override search_read to generate lines on-the-fly.
        This allows the model to be used in views without storing data.
        """
        from datetime import datetime, date as date_type

        # Parse domain to extract employee_id, date range, and month filter
        employee_ids = []
        start_date = None
        end_date = None
        filter_month = None

        if domain:
            for criterion in domain:
                if isinstance(criterion, (list, tuple)) and len(criterion) == 3:
                    field, operator, value = criterion
                    if field == 'employee_id':
                        if operator == '=':
                            employee_ids = [value]
                        elif operator == 'in':
                            employee_ids = value
                    elif field == 'date':
                        if operator == '>=':
                            # Convert string to date if needed
                            if isinstance(value, str):
                                start_date = datetime.strptime(value, '%Y-%m-%d').date()
                            elif isinstance(value, date_type):
                                start_date = value
                        elif operator == '<=':
                            # Convert string to date if needed
                            if isinstance(value, str):
                                end_date = datetime.strptime(value, '%Y-%m-%d').date()
                            elif isinstance(value, date_type):
                                end_date = value
                    elif field == 'month' and operator == '=':
                        filter_month = value

        # If no employee specified, use current user's employee
        if not employee_ids:
            if self.env.user.employee_id:
                employee_ids = [self.env.user.employee_id.id]
            else:
                return []

        # Generate balance lines for all requested employees
        all_lines = []
        for emp_id in employee_ids:
            employee = self.env['hr.employee'].browse(emp_id)
            if employee.exists():
                lines = self._get_balance_lines_for_employee(employee, start_date, end_date)
                all_lines.extend(lines)

        # Apply month filter if specified
        if filter_month:
            all_lines = [l for l in all_lines if l.get('month') == filter_month]

        # Parse and apply order parameter BEFORE offset/limit
        if order:
            # Parse order string like "date desc, id asc"
            order_fields = []
            for order_part in order.split(','):
                order_part = order_part.strip()
                if ' desc' in order_part.lower():
                    field = order_part.lower().replace(' desc', '').strip()
                    order_fields.append((field, True))  # True = descending
                elif ' asc' in order_part.lower():
                    field = order_part.lower().replace(' asc', '').strip()
                    order_fields.append((field, False))  # False = ascending
                else:
                    order_fields.append((order_part, False))  # Default ascending

            # Apply multi-field sorting
            if order_fields:
                # Sort by multiple fields, applying each in reverse order
                for field, desc in reversed(order_fields):
                    all_lines.sort(
                        key=lambda x: (x.get(field) is None, x.get(field) or 0 if isinstance(x.get(field), (int, float)) else x.get(field) or ''),
                        reverse=desc
                    )

        # Apply offset and limit AFTER sorting
        if offset:
            all_lines = all_lines[offset:]
        if limit:
            all_lines = all_lines[:limit]

        # Return only requested fields
        if fields:
            all_lines = [{k: v for k, v in line.items() if k in fields or k == 'id'} for line in all_lines]

        # Add fake IDs for UI rendering (combination of employee_id and date)
        for i, line in enumerate(all_lines):
            line['id'] = i + (offset or 0) + 1

        return all_lines

    def read(self, fields=None, load='_classic_read'):
        """Override read to prevent database access"""
        # This model doesn't have real records, return empty
        return []

    @api.model
    def search_fetch(self, domain, field_names=None, offset=0, limit=None, order=None):
        """Override to prevent DB query on non-existent table."""
        records = self.search_read(domain=domain, fields=['id'], offset=offset, limit=limit, order=order)
        return self.browse([r['id'] for r in records])

    def export_data(self, fields_to_export):
        """Override export to use virtual data instead of querying non-existent table."""
        field_names = []
        for f in fields_to_export:
            name = f[0] if isinstance(f, (list, tuple)) else f
            field_names.append(name)

        # Reconstruct domain from context
        domain = []
        emp_id = self.env.context.get('default_employee_id')
        if emp_id:
            domain = [('employee_id', '=', emp_id)]

        records = self.search_read(domain=domain, fields=field_names)

        rows = []
        for record in records:
            row = []
            for fname in field_names:
                val = record.get(fname, '')
                if val is None or val is False:
                    val = ''
                row.append(val)
            rows.append(row)

        return {'datas': rows}

    @api.model
    def web_search_read(self, domain=None, specification=None, offset=0, limit=None, order=None, count_limit=None):
        """
        Override web_search_read for Odoo 19 compatibility.
        This prevents search_fetch from trying to query the non-existent table.
        """
        # Convert specification to fields list
        fields = list(specification.keys()) if specification else None

        # Use search_read to generate data
        records = self.search_read(domain=domain, fields=fields, offset=offset, limit=limit, order=order)

        # Calculate length (for pagination)
        if count_limit:
            # Generate all records to count (without limit)
            all_records = self.search_read(domain=domain, fields=['id'])
            length = len(all_records)
        else:
            length = len(records)

        return {
            'length': length,
            'records': records,
        }

    @api.model
    def formatted_read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None):
        """Override to generate grouped data from virtual records."""
        from collections import OrderedDict

        all_records = self.search_read(domain=domain)
        if not all_records and groupby:
            return []

        # Parse aggregates
        agg_specs = list(aggregates)

        if not groupby:
            # No groupby — return single aggregate row
            group = {'__extra_domain': [(1, '=', 1)]}
            for agg in agg_specs:
                parts = agg.split(':')
                fname, func = parts[0], parts[1] if len(parts) > 1 else 'sum'
                if fname == '__count':
                    group['__count'] = len(all_records)
                elif all_records and fname in all_records[0]:
                    values = [r.get(fname, 0) or 0 for r in all_records]
                    group[agg] = sum(values) if func == 'sum' else len(values)
                else:
                    group[agg] = 0
            return [group]

        gb_field = groupby[0].split(':')[0]

        # Group records
        groups_dict = OrderedDict()
        for record in all_records:
            key = record.get(gb_field, False)
            if key not in groups_dict:
                groups_dict[key] = []
            groups_dict[key].append(record)

        # Build formatted groups
        groups = []
        for key, records in groups_dict.items():
            group = {
                groupby[0]: key,
                '__extra_domain': [(gb_field, '=', key)],
                '__count': len(records),
            }

            for agg in agg_specs:
                parts = agg.split(':')
                fname, func = parts[0], parts[1] if len(parts) > 1 else 'sum'
                if fname == '__count':
                    group['__count'] = len(records)
                elif records and fname in records[0]:
                    if fname == 'balance_cumulative':
                        # For running balance, grouped value should be the value
                        # from the latest record in the group, not the sum.
                        sorted_records = sorted(
                            records,
                            key=lambda r: (
                                r.get('date') or fields.Date.today(),
                                r.get('id') or 0,
                            )
                        )
                        group[agg] = sorted_records[-1].get('balance_cumulative', 0.0) or 0.0
                    else:
                        values = [r.get(fname, 0) or 0 for r in records]
                        if func == 'sum':
                            group[agg] = sum(values)
                        elif func == 'avg':
                            group[agg] = sum(values) / len(values) if values else 0
                        elif func in ('max', 'min'):
                            group[agg] = (max if func == 'max' else min)(values) if values else 0
                        else:
                            group[agg] = sum(values)
                else:
                    group[agg] = 0

            groups.append(group)

        # Sort groups
        reverse = False
        if order:
            for part in order.split(','):
                tokens = part.strip().split()
                if tokens[0].split(':')[0] == gb_field:
                    reverse = len(tokens) > 1 and tokens[1].lower() == 'desc'
                    break
        groups.sort(key=lambda g: g.get(groupby[0]) or '', reverse=reverse)

        # Apply offset/limit
        if offset:
            groups = groups[offset:]
        if limit:
            groups = groups[:limit]

        return groups

    @api.model
    def web_read_group(self, domain, groupby, aggregates=(), limit=None, offset=0, order=None, **kwargs):
        """Override to support grouping for virtual model without DB access."""
        if not groupby:
            return {'groups': [], 'length': 0}

        groups = self.formatted_read_group(
            domain, groupby=groupby, aggregates=aggregates,
            offset=offset, limit=limit, order=order,
        )

        # Auto-unfold: include __records for each group
        spec = kwargs.get('unfold_read_specification') or {}
        opening_info = kwargs.get('opening_info') or []

        # Build a set of unfolded group values from opening_info
        unfolded_values = set()
        for info in opening_info:
            if not info.get('folded', True):
                unfolded_values.add(info.get('value'))

        gb_field = groupby[0].split(':')[0]

        for group in groups:
            group_val = group.get(groupby[0])
            # Unfold if opening_info says so, or if auto_unfold is requested
            is_open = group_val in unfolded_values or kwargs.get('auto_unfold', False)

            if is_open and spec:
                # Get records for this group via search_read
                group_domain = list(domain) + group['__extra_domain']
                records = self.search_read(domain=group_domain, fields=list(spec.keys()) + ['id'])
                group['__records'] = records

        total = len(groups) + offset
        if limit and len(groups) == limit:
            # There might be more groups
            all_groups = self.formatted_read_group(domain, groupby=groupby, aggregates=['__count'])
            total = len(all_groups)

        return {
            'groups': groups,
            'length': total,
        }

    @api.model
    def _read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None):
        """
        Override _read_group to support graph and pivot views.
        Since this is a compute-only model, we need to generate data and perform grouping in Python.
        Returns list of tuples (group_values..., aggregate_values..., count)
        """
        # First, get all records using search_read
        all_records = self.search_read(domain=domain)

        if not all_records:
            return []

        # Compute split values for each record (needed for chart coloring)
        for record in all_records:
            # Split daily balance
            balance_delta = record.get('balance_delta', 0.0) or 0.0
            if balance_delta >= 0:
                record['balance_delta_positive'] = balance_delta
                record['balance_delta_negative'] = 0.0
            else:
                record['balance_delta_positive'] = 0.0
                record['balance_delta_negative'] = abs(balance_delta)

            # Split cumulative balance
            balance_cumulative = record.get('balance_cumulative', 0.0) or 0.0
            if balance_cumulative >= 0:
                record['balance_cumulative_positive'] = balance_cumulative
                record['balance_cumulative_negative'] = 0.0
            else:
                record['balance_cumulative_positive'] = 0.0
                record['balance_cumulative_negative'] = abs(balance_cumulative)

        # Parse aggregate fields
        aggregate_fields = []
        for agg_spec in aggregates:
            parts = agg_spec.split(':')
            fname = parts[0]
            func = parts[1] if len(parts) > 1 else 'sum'
            aggregate_fields.append((fname, func, agg_spec))

        # If no groupby, perform simple aggregation
        if not groupby:
            row = []

            # Calculate aggregates - only what was requested
            for fname, func, agg_spec in aggregate_fields:
                if fname == '__count' or fname == '*':
                    row.append(len(all_records))
                elif all_records and fname in all_records[0]:
                    values = [rec.get(fname, 0) or 0 for rec in all_records]
                    if func == 'sum':
                        row.append(sum(values))
                    elif func == 'avg':
                        row.append(sum(values) / len(values) if values else 0)
                    elif func == 'max':
                        row.append(max(values) if values else 0)
                    elif func == 'min':
                        row.append(min(values) if values else 0)
                    elif func == 'count':
                        row.append(len(values))
                    else:
                        row.append(sum(values))  # default to sum
                else:
                    row.append(0)

            # Only add count if not already in aggregates
            has_count = any(fname in ('__count', '*') for fname, _, _ in aggregate_fields)
            if not has_count:
                row.append(len(all_records))

            return [tuple(row)]

        # Group records by the groupby fields
        from collections import defaultdict
        groups = defaultdict(list)

        for record in all_records:
            # Build group key
            key_parts = []
            for gb_field in groupby:
                field_name = gb_field.split(':')[0]
                if field_name in record:
                    value = record[field_name]
                    # Handle Many2one fields - they come as [id, name]
                    if isinstance(value, (list, tuple)) and len(value) == 2:
                        key_parts.append(value)  # Keep as tuple for display
                    else:
                        key_parts.append(value)
                else:
                    key_parts.append(False)

            key = tuple(key_parts)
            groups[key].append(record)

        # Build result for each group - return as tuples
        results = []
        for group_key, group_records in groups.items():
            row = []

            # Add groupby values
            for value in group_key:
                row.append(value)

            # Calculate aggregates for this group - only what was requested
            for fname, func, agg_spec in aggregate_fields:
                if fname == '__count' or fname == '*':
                    row.append(len(group_records))
                elif group_records and fname in group_records[0]:
                    if fname == 'balance_cumulative':
                        # Running balance in grouped views should display
                        # the last chronological value in the group.
                        sorted_records = sorted(
                            group_records,
                            key=lambda r: (
                                r.get('date') or fields.Date.today(),
                                r.get('id') or 0,
                            )
                        )
                        row.append(sorted_records[-1].get('balance_cumulative', 0.0) or 0.0)
                    else:
                        values = [rec.get(fname, 0) or 0 for rec in group_records]
                        if func == 'sum':
                            row.append(sum(values))
                        elif func == 'avg':
                            row.append(sum(values) / len(values) if values else 0)
                        elif func == 'max':
                            row.append(max(values) if values else 0)
                        elif func == 'min':
                            row.append(min(values) if values else 0)
                        elif func == 'count':
                            row.append(len(values))
                        else:
                            row.append(sum(values))
                else:
                    row.append(0)

            # Only add count if not already in aggregates
            has_count = any(fname in ('__count', '*') for fname, _, _ in aggregate_fields)
            if not has_count:
                row.append(len(group_records))

            results.append(tuple(row))

        # Apply ordering if specified
        if order:
            order_fields = []
            for order_spec in order.split(','):
                parts = order_spec.strip().split()
                field = parts[0]
                direction = parts[1] if len(parts) > 1 else 'asc'
                # Find index of this field in groupby
                try:
                    idx = [gb.split(':')[0] for gb in groupby].index(field)
                    order_fields.append((idx, direction == 'desc'))
                except ValueError:
                    pass  # Field not in groupby

            for idx, reverse in reversed(order_fields):
                results.sort(key=lambda x: x[idx] if x[idx] is not False else '', reverse=reverse)

        # Apply limit and offset
        if offset:
            results = results[offset:]
        if limit:
            results = results[:limit]

        return results

    @api.model
    def _read_grouping_sets(self, domain, grouping_sets=(), aggregates=(), order=None):
        """
        Override _read_grouping_sets to support pivot views.
        This method is used by pivot views for multiple grouping levels.
        """
        # For compute-only models, we'll use _read_group for each grouping set
        all_results = []

        for groupby in grouping_sets:
            results = self._read_group(
                domain=domain,
                groupby=groupby,
                aggregates=aggregates,
                order=order
            )
            all_results.extend(results)

        return all_results
