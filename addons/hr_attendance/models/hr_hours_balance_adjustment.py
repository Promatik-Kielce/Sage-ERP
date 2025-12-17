# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class HrHoursBalanceAdjustment(models.Model):
    _name = 'hr.hours.balance.adjustment'
    _description = 'Hours Balance Manual Adjustment'
    _order = 'date desc, id desc'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
        index=True
    )

    adjustment_amount = fields.Float(
        string='Adjustment (Hours)',
        required=True,
        help='Positive to add hours, negative to subtract. Example: 8.5 or -4.25'
    )

    reason = fields.Text(
        string='Reason',
        required=True,
        help='Explain why this adjustment is being made'
    )

    date = fields.Date(
        string='Adjustment Date',
        required=True,
        default=fields.Date.context_today,
        help='Date when this adjustment applies'
    )

    original_balance = fields.Float(
        string='Balance Before',
        readonly=True,
        help='Hours balance before this adjustment'
    )

    new_balance = fields.Float(
        string='Balance After',
        readonly=True,
        help='Hours balance after this adjustment'
    )

    user_id = fields.Many2one(
        'res.users',
        string='Adjusted By',
        required=True,
        default=lambda self: self.env.user,
        readonly=True
    )

    company_id = fields.Many2one(
        'res.company',
        related='employee_id.company_id',
        store=True,
        readonly=True
    )

    @api.constrains('adjustment_amount')
    def _check_adjustment_amount(self):
        for record in self:
            if record.adjustment_amount == 0:
                raise ValidationError(_('Adjustment amount cannot be zero.'))

    @api.constrains('reason')
    def _check_reason(self):
        for record in self:
            if not record.reason or len(record.reason.strip()) < 10:
                raise ValidationError(_('Reason must be at least 10 characters.'))

    @api.model_create_multi
    def create(self, vals_list):
        """Calculate original and new balance before creating record"""
        for vals in vals_list:
            employee = self.env['hr.employee'].browse(vals['employee_id'])

            # Compute original balance (before adjustment)
            original_balance = employee._compute_hours_balance_value()
            vals['original_balance'] = original_balance

            # Compute new balance (after adjustment)
            vals['new_balance'] = original_balance + vals['adjustment_amount']

        return super().create(vals_list)

    def name_get(self):
        """Custom display name"""
        result = []
        for record in self:
            name = f"{record.employee_id.name} - {record.adjustment_amount:+.2f}h on {record.date}"
            result.append((record.id, name))
        return result
