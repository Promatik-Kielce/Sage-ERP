from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrBusinessTrip(models.Model):
    _name = "hr.business.trip"
    _description = "Business Trip"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, id desc"

    name = fields.Char(
        string="Numer delegacji",
        compute="_compute_name",
        store=True,
    )

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        tracking=True,
    )

    company_id = fields.Many2one(
        "res.company",
        related="employee_id.company_id",
        store=True,
        readonly=True,
    )

    project_id = fields.Many2one(
        "project.project",
        string="Project",
        tracking=True,
    )

    date_from = fields.Date(
        string="Date From",
        required=True,
        tracking=True,
    )

    date_to = fields.Date(
        string="Date To",
        required=True,
        tracking=True,
    )

    note = fields.Text(string="Description")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("approved", "Approved"),
            ("refused", "Refused"),
        ],
        string="Status",
        default="draft",
        tracking=True,
    )

    attendance_ids = fields.One2many(
        "hr.attendance",
        "business_trip_id",
        string="Attendances",
    )

    working_days_count = fields.Integer(
        string="Working Days",
        compute="_compute_working_days_count",
        store=True,
    )

    calendar_color = fields.Integer(
        string="Calendar Color",
        compute="_compute_calendar_color",
    )

    @api.depends("employee_id", "project_id", "date_from", "date_to")
    def _compute_name(self):
        for rec in self:
            if rec.employee_id and rec.date_from and rec.date_to:
                parts = [rec.employee_id.name]
                if rec.project_id:
                    parts.append(rec.project_id.name)
                parts.append(f"{rec.date_from} - {rec.date_to}")
                rec.name = " | ".join(parts)
            else:
                rec.name = _("New Business Trip")

    @api.depends("date_from", "date_to")
    def _compute_working_days_count(self):
        for rec in self:
            count = 0
            if rec.date_from and rec.date_to and rec.date_from <= rec.date_to:
                current = rec.date_from
                while current <= rec.date_to:
                    if current.weekday() < 5:
                        count += 1
                    current += timedelta(days=1)
            rec.working_days_count = count

    @api.depends("state")
    def _compute_calendar_color(self):
        for rec in self:
            if rec.state == "approved":
                rec.calendar_color = 7
            elif rec.state == "refused":
                rec.calendar_color = 1
            else:
                rec.calendar_color = 2

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError(_("Date To cannot be earlier than Date From."))

    @api.constrains("employee_id", "date_from", "date_to", "state")
    def _check_overlaps(self):
        for rec in self.filtered(lambda r: r.state != "refused"):
            domain = [
                ("id", "!=", rec.id),
                ("employee_id", "=", rec.employee_id.id),
                ("state", "!=", "refused"),
                ("date_from", "<=", rec.date_to),
                ("date_to", ">=", rec.date_from),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _("This employee already has another business trip in the selected period.")
                )

    def _unlink_trip_attendances(self):
        """Usuń tylko attendance wygenerowane przez delegację wraz z kartami pracy."""
        attendances = self.env["hr.attendance"].search([
            ("business_trip_id", "in", self.ids),
            ("is_business_trip", "=", True),
        ])

        timesheets = self.env["account.analytic.line"].search([
            ("attendance_id", "in", attendances.ids),
        ])
        timesheets.unlink()

        attendances.unlink()

    def _create_trip_timesheet(self, attendance, day_date):
        """Utwórz kartę pracy dla attendance delegacyjnego."""
        self.ensure_one()

        if not self.project_id:
            return

        employee = self.employee_id
        if not employee:
            return

        user_id = employee.user_id.id if employee.user_id else self.env.user.id

        self.env["account.analytic.line"].create({
            "employee_id": employee.id,
            "user_id": user_id,
            "project_id": self.project_id.id,
            "date": day_date,
            "name": self.note or _("Delegacja: %s") % self.project_id.display_name,
            "unit_amount": 8.0,
            "attendance_id": attendance.id,
        })

        attendance._compute_timesheet_hours()
        attendance._compute_main_project()
        attendance._compute_current_project()

    def _unlink_trip_timesheets(self):
        """Usuń karty pracy powiązane z attendance wygenerowanymi z delegacji."""
        attendances = self.env["hr.attendance"].search([
            ("business_trip_id", "in", self.ids),
            ("is_business_trip", "=", True),
        ])
        timesheets = self.env["account.analytic.line"].search([
            ("attendance_id", "in", attendances.ids),
        ])
        timesheets.unlink()

    def unlink(self):
        """Przy usuwaniu delegacji usuń też wygenerowane attendance."""
        self._unlink_trip_attendances()
        return super().unlink()

    def write(self, vals):
        """
        Jeśli edytowana jest już zatwierdzona delegacja, zsynchronizuj attendance
        i timesheety z nowymi danymi.
        """
        sync_fields = {"employee_id", "project_id", "date_from", "date_to", "note"}

        needs_sync = any(field in vals for field in sync_fields)
        approved_before = self.filtered(lambda r: r.state == "approved")

        result = super().write(vals)

        if needs_sync and approved_before:
            approved_before._sync_approved_trip_attendances()

        return result

    def action_approve(self):
        for rec in self:
            if rec.state == "approved":
                continue
            rec._generate_attendances()
            rec.state = "approved"

    def action_refuse(self):
        for rec in self:
            rec._unlink_trip_attendances()
            rec.state = "refused"

    def action_reset_to_draft(self):
        for rec in self:
            rec._unlink_trip_attendances()
            rec.state = "draft"

    def _get_trip_workdays(self):
        """Zwróć zbiór dni roboczych delegacji."""
        self.ensure_one()
        workdays = set()
        current = self.date_from
        while current <= self.date_to:
            if current.weekday() < 5:
                workdays.add(current)
            current += timedelta(days=1)
        return workdays

    def _sync_approved_trip_attendances(self):
        """
        Synchronizuje attendance/timesheety dla już zatwierdzonej delegacji:
        - usuwa nieaktualne dni,
        - aktualizuje istniejące,
        - dodaje brakujące.
        """
        Attendance = self.env["hr.attendance"]
        Timesheet = self.env["account.analytic.line"]

        for rec in self:
            if rec.state != "approved":
                continue
            if not rec.employee_id or not rec.date_from or not rec.date_to:
                continue

            tz_name = self.env.user.tz or "UTC"
            tz = pytz.timezone(tz_name)

            valid_workdays = rec._get_trip_workdays()

            existing_attendances = Attendance.search([
                ("business_trip_id", "=", rec.id),
                ("is_business_trip", "=", True),
            ])

            # Usuń attendance, które nie należą już do nowego zakresu / pracownika
            for att in existing_attendances:
                att_local_date = pytz.utc.localize(att.check_in).astimezone(tz).date() if att.check_in.tzinfo is None else att.check_in.astimezone(tz).date()

                if att.employee_id != rec.employee_id or att_local_date not in valid_workdays:
                    Timesheet.search([("attendance_id", "=", att.id)]).unlink()
                    att.unlink()

            # Wygeneruj / zaktualizuj aktualny zestaw attendance
            rec._generate_attendances()

    def _generate_attendances(self):
        self.ensure_one()

        employee = self.employee_id
        if not employee:
            return

        tz_name = self.env.user.tz or "UTC"
        tz = pytz.timezone(tz_name)

        current = self.date_from
        while current <= self.date_to:
            if current.weekday() < 5:  # Mon-Fri
                check_in_utc, check_out_utc = self._get_utc_datetimes_for_day(current, tz)

                # Najpierw szukaj attendance tej konkretnej delegacji dla tego dnia
                existing = self.env["hr.attendance"].search([
                    ("business_trip_id", "=", self.id),
                    ("is_business_trip", "=", True),
                    ("check_in", "=", check_in_utc),
                    ("check_out", "=", check_out_utc),
                ], limit=1)

                # Fallback: jeśli nie ma, szukaj kolidującego attendance pracownika
                if not existing:
                    existing = self.env["hr.attendance"].search([
                        ("employee_id", "=", employee.id),
                        ("check_in", "<", check_out_utc),
                        ("check_out", ">", check_in_utc),
                    ], limit=1)

                vals = {
                    "employee_id": employee.id,
                    "check_in": check_in_utc,
                    "check_out": check_out_utc,
                    "is_business_trip": True,
                    "business_trip_id": self.id,
                    "project_id": self.project_id.id if self.project_id else False,
                }

                attendance = False

                if existing:
                    if existing.is_business_trip:
                        old_timesheets = self.env["account.analytic.line"].search([
                            ("attendance_id", "=", existing.id),
                        ])
                        old_timesheets.unlink()

                        existing.write(vals)
                        attendance = existing
                else:
                    attendance = self.env["hr.attendance"].create(vals)

                if attendance:
                    self._create_trip_timesheet(attendance, current)

            current += timedelta(days=1)

    def _get_utc_datetimes_for_day(self, day_date, tz):
        local_check_in = tz.localize(datetime.combine(day_date, time(8, 0, 0)))
        local_check_out = tz.localize(datetime.combine(day_date, time(16, 0, 0)))

        check_in_utc = local_check_in.astimezone(pytz.UTC).replace(tzinfo=None)
        check_out_utc = local_check_out.astimezone(pytz.UTC).replace(tzinfo=None)
        return check_in_utc, check_out_utc