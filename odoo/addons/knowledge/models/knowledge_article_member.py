from odoo import fields, models


class KnowledgeArticleMember(models.Model):
    _name = "knowledge.article.member"
    _description = "Knowledge Article Member"

    article_id = fields.Many2one(
        "knowledge.article",
        string="Article",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Member",
        required=True,
        index=True,
    )
    permission = fields.Selection(
        [
            ("read", "Can Read"),
            ("write", "Can Write"),
            ("admin", "Admin"),
        ],
        string="Permission",
        required=True,
        default="read",
    )

    _sql_constraints = [
        (
            "unique_member",
            "UNIQUE(article_id, partner_id)",
            "A member can only have one permission entry per article.",
        ),
    ]
