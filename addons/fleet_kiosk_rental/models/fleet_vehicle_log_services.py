# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class FleetVehicleLogServices(models.Model):
    _inherit = 'fleet.vehicle.log.services'

    is_rental = fields.Boolean(
        string="Car Rental",
        default=False,
        help="Set when this log was created through the kiosk car rental flow.")
    employee_id = fields.Many2one(
        'hr.employee', string="Rented By", index=True)
    rental_start = fields.Datetime(string="Taken On")
    rental_return = fields.Datetime(string="Returned On")
    project_number_ids = fields.One2many(
        'fleet.rental.project', 'service_id', string="Project Numbers")

    def _get_employee_open_rental(self, employee):
        """Return the employee's current open rental, if any."""
        if not employee:
            return self.browse()
        return self.sudo().search([
            ('is_rental', '=', True),
            ('state', '=', 'running'),
            ('rental_return', '=', False),
            ('employee_id', '=', employee.id),
        ], limit=1, order='rental_start desc')
