# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class HrHoursBalanceAdjustmentWizard(models.TransientModel):
    _name = 'hr.hours.balance.adjustment.wizard'
    _description = 'Wizard to Adjust Employee Hours Balance'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True
    )

    current_balance = fields.Float(
        string='Current Balance',
        compute='_compute_current_balance',
        readonly=True,
        help='Current hours balance before adjustment'
    )

    adjustment_amount = fields.Float(
        string='Adjustment Amount (Hours)',
        required=True,
        help='Positive to add hours, negative to subtract'
    )

    reason = fields.Text(
        string='Reason',
        required=True,
        help='Explain why you are making this adjustment'
    )

    date = fields.Date(
        string='Adjustment Date',
        required=True,
        default=fields.Date.context_today,
        help='Date when this adjustment applies'
    )

    preview_new_balance = fields.Float(
        string='New Balance (Preview)',
        compute='_compute_preview_new_balance',
        readonly=True
    )

    @api.depends('employee_id')
    def _compute_current_balance(self):
        for wizard in self:
            if wizard.employee_id:
                wizard.current_balance = wizard.employee_id.hours_balance
            else:
                wizard.current_balance = 0.0

    @api.depends('current_balance', 'adjustment_amount')
    def _compute_preview_new_balance(self):
        for wizard in self:
            wizard.preview_new_balance = wizard.current_balance + wizard.adjustment_amount

    def action_apply_adjustment(self):
        """Create the adjustment record"""
        self.ensure_one()

        # Create adjustment record
        adjustment = self.env['hr.hours.balance.adjustment'].create({
            'employee_id': self.employee_id.id,
            'adjustment_amount': self.adjustment_amount,
            'reason': self.reason,
            'date': self.date,
        })

        # Show success message and return to employee form
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Adjustment Applied',
                'message': f'Hours balance adjusted by {self.adjustment_amount:+.2f}h for {self.employee_id.name}',
                'type': 'success',
                'sticky': False,
            }
        }
