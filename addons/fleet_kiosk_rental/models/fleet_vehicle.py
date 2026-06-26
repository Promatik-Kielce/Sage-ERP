# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


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
            data.append({
                'id': vehicle.id,
                'name': vehicle.display_name,
                'license_plate': vehicle.license_plate or '',
                'is_rented': is_rented,
                'renter_name': rental.employee_id.name if rental else False,
                'insurance_expired': insurance_expired,
                'checkup_overdue': checkup_overdue,
                'available': not (is_rented or insurance_expired or checkup_overdue),
            })
        return data
