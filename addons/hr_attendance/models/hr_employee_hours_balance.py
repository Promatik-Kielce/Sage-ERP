# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta
from collections import defaultdict
import pytz

from odoo import models, fields, api, _
from odoo.tools import format_date


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
    day_of_week = fields.Char(string='Day', compute='_compute_day_details', store=False)
    worked_hours = fields.Float(string='Worked Hours')
    expected_hours = fields.Float(string='Expected Hours')
    is_weekend = fields.Boolean(string='Weekend')
    is_public_holiday = fields.Boolean(string='Public Holiday')
    has_approved_leave = fields.Boolean(string='Has Leave')
    leave_name = fields.Char(string='Leave Type')
    balance_delta = fields.Float(string='Daily +/-', help='Change in balance for this day')
    balance_cumulative = fields.Float(string='Total Balance', help='Running total balance up to this date')
    notes = fields.Text(string='Calculation Notes')
    attendance_count = fields.Integer(string='# Attendances')

    @api.depends('date')
    def _compute_day_details(self):
        """Compute day of week name"""
        for line in self:
            if line.date:
                line.day_of_week = format_date(self.env, line.date, date_format='EEE')  # Mon, Tue, etc.
            else:
                line.day_of_week = ''

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
            end_date = datetime.now().date()

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
            att_date = att.check_in.date()
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

        # Calculate balance for each day
        balance_lines = []
        cumulative_balance = 0.0

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
            public_holiday = self.env['resource.calendar.leaves'].search([
                ('calendar_id', '=', calendar.id),
                ('date_from', '<=', datetime_end_naive),
                ('date_to', '>=', datetime_start_naive),
                '|', ('resource_id', '=', False), ('resource_id', '=', employee.resource_id.id)
            ], limit=1)
            is_public_holiday = bool(public_holiday)

            # Check for approved leave
            has_approved_leave = current_date in leave_dates
            leave_name = leave_dates.get(current_date, '')

            # Get expected hours from calendar for this day
            if is_public_holiday or has_approved_leave or is_weekend:
                expected_hours = 0.0
            else:
                # Get work intervals for this day (requires timezone-aware datetimes)
                work_intervals = calendar._work_intervals_batch(
                    datetime_start_utc, datetime_end_utc,
                    resources=employee.resource_id
                )[employee.resource_id.id]
                expected_hours = sum(
                    (stop - start).total_seconds() / 3600.0
                    for start, stop, meta in work_intervals
                )

            # Get actual worked hours
            day_attendances = attendance_by_date.get(current_date, [])
            worked_hours = sum(att.worked_hours for att in day_attendances)
            attendance_count = len(day_attendances)

            # Check if any attendance is technical (absence detection)
            has_technical_attendance = any(att.in_mode == 'technical' for att in day_attendances)

            # Calculate balance delta based on rules
            if is_public_holiday:
                # Public holidays: no penalty, no bonus
                balance_delta = 0.0
                notes = _('Public holiday - no hours counted')
            elif has_approved_leave:
                # Approved leave: no penalty, no bonus
                balance_delta = 0.0
                notes = _('Approved leave: %s') % leave_name
            elif is_weekend:
                # Weekend: all worked hours are bonus
                balance_delta = worked_hours
                if worked_hours > 0:
                    notes = _('Weekend work: +%s hours bonus') % round(worked_hours, 2)
                else:
                    notes = _('Weekend - no work expected')
            else:
                # Weekday (Mon-Fri): difference between worked and expected
                balance_delta = worked_hours - expected_hours

                if attendance_count == 0 and expected_hours > 0:
                    notes = _('Absent: -%s hours (no attendance recorded)') % round(expected_hours, 2)
                elif has_technical_attendance:
                    notes = _('Absent: -%s hours (absence detected by system)') % round(expected_hours, 2)
                elif worked_hours >= expected_hours:
                    overtime = worked_hours - expected_hours
                    notes = _('Worked %sh, expected %sh: +%sh overtime') % (
                        round(worked_hours, 2), round(expected_hours, 2), round(overtime, 2)
                    )
                else:
                    undertime = expected_hours - worked_hours
                    notes = _('Worked %sh, expected %sh: -%sh undertime') % (
                        round(worked_hours, 2), round(expected_hours, 2), round(undertime, 2)
                    )

            cumulative_balance += balance_delta

            balance_lines.append({
                'employee_id': employee.id,
                'date': current_date,
                'worked_hours': worked_hours,
                'expected_hours': expected_hours,
                'is_weekend': is_weekend,
                'is_public_holiday': is_public_holiday,
                'has_approved_leave': has_approved_leave,
                'leave_name': leave_name,
                'balance_delta': balance_delta,
                'balance_cumulative': cumulative_balance,
                'notes': notes,
                'attendance_count': attendance_count,
            })

            current_date += timedelta(days=1)

        return balance_lines

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """
        Override search_read to generate lines on-the-fly.
        This allows the model to be used in views without storing data.
        """
        from datetime import datetime, date as date_type

        # Parse domain to extract employee_id and date range
        employee_ids = []
        start_date = None
        end_date = None

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

        # Apply offset and limit
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
