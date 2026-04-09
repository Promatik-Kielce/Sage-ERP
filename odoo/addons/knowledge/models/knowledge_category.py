from odoo import api, fields, models


class KnowledgeCategory(models.Model):
    _name = "knowledge.category"
    _description = "Knowledge Shared Category"
    _parent_name = "parent_id"
    _parent_store = True
    _order = "sequence, name"

    name = fields.Char("Name", required=True)
    description = fields.Text("Description")
    parent_id = fields.Many2one(
        "knowledge.category",
        "Parent Category",
        index=True,
        ondelete="cascade",
    )
    child_ids = fields.One2many(
        "knowledge.category", "parent_id", string="Sub-categories"
    )
    parent_path = fields.Char(index=True, unaccent=False)
    sequence = fields.Integer("Sequence", default=10)
    article_count = fields.Integer(
        "Article Count", compute="_compute_article_count"
    )

    @api.depends("name")
    def _compute_article_count(self):
        # Unsaved (NewId) records cannot be queried — assign 0 immediately
        saved = self.filtered(lambda c: isinstance(c.id, int))
        for category in self - saved:
            category.article_count = 0
        if not saved:
            return
        data = self.env["knowledge.article"].read_group(
            domain=[("knowledge_category_id", "in", saved.ids)],
            fields=["knowledge_category_id"],
            groupby=["knowledge_category_id"],
        )
        counts = {row["knowledge_category_id"][0]: row["knowledge_category_id_count"] for row in data}
        for category in saved:
            category.article_count = counts.get(category.id, 0)
