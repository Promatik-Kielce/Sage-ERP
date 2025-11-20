# Part of Sage-ERP. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class IrActionsActWindowView(models.Model):
    _inherit = 'ir.actions.act_window.view'

    view_mode = fields.Selection(
        selection_add=[('gantt', 'Gantt')],
        ondelete={'gantt': 'cascade'}
    )
