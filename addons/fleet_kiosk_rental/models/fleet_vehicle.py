# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import timedelta

from odoo import api, fields, models


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    insurance_expiry_date = fields.Date(
        string="Insurance Expiry",
        tracking=True,
        help="Date on which the vehicle insurance expires. Past this date the car "
             "can no longer be rented from the kiosk.")
    next_technical_checkup_date = fields.Date(
        string="Next Technical Checkup",
        tracking=True,
        help="Date of the next mandatory technical inspection. Past this date the "
             "car can no longer be rented from the kiosk.")
    insurance_reminder_date = fields.Date(
        copy=False,
        help="Insurance expiry date an upcoming-expiry reminder was already sent for. "
             "Cleared automatically when the expiry date changes so a new reminder can fire.")
    checkup_reminder_date = fields.Date(
        copy=False,
        help="Technical checkup date an upcoming-expiry reminder was already sent for. "
             "Cleared automatically when the checkup date changes so a new reminder can fire.")
    rental_state = fields.Selection(
        selection=[
            ('parking', 'Parking'),
            ('delegation', 'Delegation'),
            ('service', 'Service'),
        ],
        string="Rental Status",
        default='parking',
        required=True,
        tracking=True,
        group_expand=True,
        help="Parking: available on site. Delegation: currently rented by an "
             "employee. Service: at the mechanic or otherwise unavailable (set "
             "manually).")

    def _get_open_rental(self):
        """Return the open rental log for this vehicle (running, not yet returned)."""
        self.ensure_one()
        return self.env['fleet.vehicle.log.services'].sudo().search([
            ('vehicle_id', '=', self.id),
            ('is_rental', '=', True),
            ('state', '=', 'running'),
            ('rental_return', '=', False),
        ], limit=1, order='rental_start desc')

    def _kiosk_rental_data(self):
        """Build the car list payload consumed by the kiosk frontend."""
        today = fields.Date.context_today(self)
        data = []
        for vehicle in self:
            rental = vehicle._get_open_rental()
            is_rented = bool(rental)
            insurance_expired = bool(
                vehicle.insurance_expiry_date and vehicle.insurance_expiry_date < today)
            checkup_overdue = bool(
                vehicle.next_technical_checkup_date and vehicle.next_technical_checkup_date < today)
            in_service = vehicle.rental_state == 'service'
            data.append({
                'id': vehicle.id,
                'name': vehicle.display_name,
                'license_plate': vehicle.license_plate or '',
                'is_rented': is_rented,
                'renter_name': rental.employee_id.name if rental else False,
                'insurance_expired': insurance_expired,
                'checkup_overdue': checkup_overdue,
                'in_service': in_service,
                'available': not (is_rented or insurance_expired or checkup_overdue or in_service),
            })
        return data

    def _expiry_reminder_recipient_emails(self):
        """Comma-separated emails of Fleet Officers + Administrators to warn about
        upcoming insurance / technical-checkup expiry."""
        groups = (self.env.ref('fleet.fleet_group_user')
                  | self.env.ref('fleet.fleet_group_manager'))
        users = groups.all_user_ids.filtered('email')
        return ','.join(users.mapped('email'))

    @api.model
    def _cron_expiry_reminders(self):
        """Email Fleet Officers/Administrators when a vehicle's insurance or technical
        checkup is due within the configured lead time. Runs daily; each expiry date is
        reminded about once (tracked via *_reminder_date), re-arming if the date changes."""
        lead = int(self.env['ir.config_parameter'].sudo().get_param(
            'fleet_kiosk_rental.expiry_reminder_lead_days', 30))
        today = fields.Date.context_today(self)
        horizon = today + timedelta(days=lead)
        recipients = self._expiry_reminder_recipient_emails()
        if not recipients:
            return
        template = self.env.ref(
            'fleet_kiosk_rental.mail_template_expiry_reminder', raise_if_not_found=False)
        if not template:
            return
        checks = [
            ('insurance_expiry_date', 'insurance_reminder_date', 'insurance'),
            ('next_technical_checkup_date', 'checkup_reminder_date', 'checkup'),
        ]
        for date_field, reminder_field, reason in checks:
            vehicles = self.sudo().search([(date_field, '!=', False), (date_field, '<=', horizon)])
            for vehicle in vehicles:
                expiry_date = vehicle[date_field]
                if vehicle[reminder_field] == expiry_date:
                    continue
                template.with_context(
                    reason=reason, expiry_date=expiry_date, email_to=recipients,
                ).send_mail(vehicle.id, force_send=True, email_values={'email_to': recipients})
                vehicle[reminder_field] = expiry_date
