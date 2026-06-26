# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class FleetRentalProject(models.Model):
    _name = 'fleet.rental.project'
    _description = 'Car Rental Project Number'

    service_id = fields.Many2one(
        'fleet.vehicle.log.services', string="Rental",
        required=True, ondelete='cascade', index=True)
    name = fields.Char(
        string="Project Number", required=True,
        help="Free-text project/site number. Intentionally not linked to any "
             "project record, since employees may visit very old projects that "
             "are no longer in the system.")
