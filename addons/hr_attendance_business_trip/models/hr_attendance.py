from odoo import models, fields


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    is_business_trip = fields.Boolean(
        string='Delegacja',
        default=False,
        index=True,
    )

    business_trip_id = fields.Many2one(
        'hr.business.trip',
        string='Delegacja',
        ondelete='set null',
        index=True,
    )