from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    group_knowledge_user = fields.Boolean(
        string="Knowledge Articles",
        implied_group="knowledge.group_knowledge_user",
        help="When enabled, all internal users can access Knowledge articles.",
    )
