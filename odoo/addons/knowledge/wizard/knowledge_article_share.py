from odoo import api, fields, models, Command
from odoo.tools.translate import _


class KnowledgeArticleShare(models.TransientModel):
    _name = "knowledge.article.share"
    _description = "Share Knowledge Article"

    article_id = fields.Many2one(
        "knowledge.article",
        string="Article",
        required=True,
        default=lambda self: self.env.context.get("active_id"),
    )
    partner_ids = fields.Many2many(
        "res.partner",
        string="Share With",
        required=True,
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
    send_notification = fields.Boolean(
        "Send Notification",
        default=True,
    )

    def action_share(self):
        """Add selected partners as members of the article."""
        self.ensure_one()
        MemberModel = self.env["knowledge.article.member"]

        for partner in self.partner_ids:
            existing = MemberModel.search(
                [
                    ("article_id", "=", self.article_id.id),
                    ("partner_id", "=", partner.id),
                ],
                limit=1,
            )
            if existing:
                existing.write({"permission": self.permission})
            else:
                MemberModel.create(
                    {
                        "article_id": self.article_id.id,
                        "partner_id": partner.id,
                        "permission": self.permission,
                    }
                )

        if self.send_notification:
            partner_names = ", ".join(self.partner_ids.mapped("name"))
            self.article_id.message_post(
                body=_(
                    "Article shared with %(partners)s (%(perm)s access).",
                    partners=partner_names,
                    perm=dict(self._fields["permission"].selection).get(
                        self.permission
                    ),
                ),
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

        return {"type": "ir.actions.act_window_close"}
