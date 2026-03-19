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

    def _compute_color(self):
        super()._compute_color()
        for attendance in self:
            if attendance.is_business_trip:
                attendance.color = 5