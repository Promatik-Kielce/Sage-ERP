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

    # Split fields for chart coloring
    balance_delta_positive = fields.Float(string='Daily + (Surplus)', compute='_compute_split_values', store=False, group_operator='sum')
    balance_delta_negative = fields.Float(string='Daily - (Deficit)', compute='_compute_split_values', store=False, group_operator='sum')
    balance_cumulative_positive = fields.Float(string='Balance + (Surplus)', compute='_compute_split_values', store=False, group_operator='sum')
    balance_cumulative_negative = fields.Float(string='Balance - (Deficit)', compute='_compute_split_values', store=False, group_operator='sum')

    @api.depends('date')
    def _compute_day_details(self):
        """Compute day of week name"""
        for line in self:
            if line.date:
                line.day_of_week = format_date(self.env, line.date, date_format='EEE')  # Mon, Tue, etc.
            else:
                line.day_of_week = ''

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
                # Public holidays: worked hours count as bonus
                balance_delta = worked_hours
                if worked_hours > 0:
                    notes = _('Public holiday work: +%s hours bonus') % round(worked_hours, 2)
                else:
                    notes = _('Public holiday - no work expected')
            elif has_approved_leave:
                # Approved leave: worked hours count as bonus
                balance_delta = worked_hours
                if worked_hours > 0:
                    notes = _('Worked on leave (%s): +%s hours bonus') % (leave_name, round(worked_hours, 2))
                else:
                    notes = _('On approved leave: %s') % leave_name
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
