import logging

from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)

ARTICLE_PERMISSION_LEVELS = [
    ("none", "No Access"),
    ("read", "Can Read"),
    ("write", "Can Write"),
    ("admin", "Admin"),
]


class KnowledgeArticle(models.Model):
    _name = "knowledge.article"
    _description = "Knowledge Article"
    _inherit = [
        "mail.thread",
        "mail.activity.mixin",
        "html.field.history.mixin",
        "ir.attachment.action_download",
    ]
    _order = "name, id"
    _parent_store = True
    _check_company_auto = True
    _mail_post_access = "read"

    # === Identity ===
    name = fields.Char(
        "Title",
        required=True,
        tracking=True,
        default=lambda self: _("Untitled"),
    )
    icon = fields.Char("Icon", help="Emoji character used as article icon")
    cover_image = fields.Binary("Cover Image", attachment=True)
    color = fields.Integer("Color Index")

    # === Content ===
    body = fields.Html(
        "Content",
        sanitize_tags=False,
        sanitize_attributes=False,
    )
    full_width = fields.Boolean("Full Width", default=False)

    # === Hierarchy ===
    parent_id = fields.Many2one(
        "knowledge.article",
        "Parent Article",
        index=True,
        ondelete="cascade",
        tracking=True,
    )
    child_ids = fields.One2many(
        "knowledge.article", "parent_id", "Child Articles"
    )
    parent_path = fields.Char(index=True, unaccent=False)
    sequence = fields.Integer("Sequence", default=10)

    # === Organization ===
    category = fields.Selection(
        [
            ("workspace", "Workspace"),
            ("shared", "Shared"),
            ("private", "Private"),
        ],
        string="Section",
        default="private",
        required=True,
        tracking=True,
    )
    knowledge_category_id = fields.Many2one(
        "knowledge.category",
        string="Shared Category",
        help="Topic category within the Shared section",
        index=True,
        tracking=True,
    )

    # === Ownership & Members ===
    owner_id = fields.Many2one(
        "res.users",
        "Owner",
        default=lambda self: self.env.user,
        required=True,
        index=True,
        tracking=True,
    )
    member_ids = fields.One2many(
        "knowledge.article.member",
        "article_id",
        "Members",
    )

    # === User-specific permission (computed) ===
    user_permission = fields.Selection(
        ARTICLE_PERMISSION_LEVELS,
        compute="_compute_user_permission",
        search="_search_user_permission",
        string="My Permission",
    )
    user_has_write_access = fields.Boolean(
        compute="_compute_user_permission",
    )
    user_has_admin_access = fields.Boolean(
        compute="_compute_user_permission",
    )

    # === Favorites ===
    favorite_user_ids = fields.Many2many(
        "res.users",
        "knowledge_article_favorite_rel",
        "article_id",
        "user_id",
        string="Favorited By",
        copy=False,
    )
    is_favorite = fields.Boolean(
        compute="_compute_is_favorite",
        inverse="_inverse_is_favorite",
        search="_search_is_favorite",
        compute_sudo=True,
        string="Favorite",
    )

    # === Template ===
    is_template = fields.Boolean("Is Template", default=False, tracking=True)

    # === Properties (Structured Items) ===
    article_properties_definition = fields.PropertiesDefinition(
        "Item Properties"
    )
    article_properties = fields.Properties(
        "Properties",
        definition="parent_id.article_properties_definition",
    )

    # === State / Lifecycle ===
    active = fields.Boolean(default=True)
    is_trashed = fields.Boolean("Trashed", default=False, tracking=True)
    trashed_date = fields.Datetime("Trashed Date")

    # === Lock ===
    is_locked = fields.Boolean("Locked", default=False, tracking=True)
    locked_by = fields.Many2one("res.users", "Locked By")

    # === Multi-company ===
    company_id = fields.Many2one(
        "res.company",
        "Company",
        default=lambda self: self.env.company,
        index=True,
    )

    # === Comments ===
    message_count = fields.Integer(
        "Comments",
        compute="_compute_message_count",
    )

    @api.depends("message_ids")
    def _compute_message_count(self):
        for article in self:
            article.message_count = len(
                article.message_ids.filtered(
                    lambda m: m.message_type in ("comment", "email")
                )
            )

    # === Constraints ===
    @api.constrains("parent_id")
    def _check_parent_id(self):
        if self._has_cycle():
            raise ValidationError(
                _("Error: an article cannot be its own parent.")
            )

    # -------------------------------------------------------------------------
    # VERSIONED FIELDS (html.field.history.mixin)
    # -------------------------------------------------------------------------

    @api.model
    def _get_versioned_fields(self):
        return ["body"]

    # -------------------------------------------------------------------------
    # COMPUTE: PERMISSIONS
    # -------------------------------------------------------------------------

    @api.depends_context("uid")
    def _compute_user_permission(self):
        user = self.env.user
        is_manager = user.has_group("knowledge.group_knowledge_manager")

        for article in self:
            if is_manager:
                article.user_permission = "admin"
                article.user_has_write_access = True
                article.user_has_admin_access = True
                continue

            if article.owner_id == user:
                article.user_permission = "admin"
                article.user_has_write_access = True
                article.user_has_admin_access = True
                continue

            permission = article._resolve_member_permission(user)

            if not permission:
                if article.category == "workspace":
                    permission = "write"
                elif article.category == "shared":
                    permission = "read"

            article.user_permission = permission or "none"
            article.user_has_write_access = permission in ("write", "admin")
            article.user_has_admin_access = permission == "admin"

    def _resolve_member_permission(self, user):
        """Walk up parent chain to find nearest membership for user."""
        self.ensure_one()
        partner = user.partner_id

        if self.parent_path:
            ancestor_ids = [
                int(x) for x in self.parent_path.split("/") if x
            ]
        else:
            ancestor_ids = [self.id]

        members = (
            self.env["knowledge.article.member"]
            .sudo()
            .search(
                [
                    ("article_id", "in", ancestor_ids),
                    ("partner_id", "=", partner.id),
                ]
            )
        )

        if not members:
            return False

        # Deepest (most specific) membership wins
        for article_id in reversed(ancestor_ids):
            member = members.filtered(
                lambda m, aid=article_id: m.article_id.id == aid
            )
            if member:
                return member[0].permission

        return False

    def _search_user_permission(self, operator, value):
        """Search implementation used by record rules and UI filters."""
        if operator not in ("=", "!=", "in", "not in"):
            raise UserError(
                _("Unsupported operator for permission search: %s", operator)
            )
        # For record rules we return a domain that filters visible articles
        user = self.env.user
        if user.has_group("knowledge.group_knowledge_manager"):
            return [(1, "=", 1)]

        if operator == "=" and value == "none":
            # Articles user cannot see — invert the visible domain
            return [
                ("category", "!=", "workspace"),
                ("owner_id", "!=", user.id),
                ("member_ids.partner_id", "!=", user.partner_id.id),
            ]

        # Default: return articles the user can see
        return [
            "|",
            ("category", "=", "workspace"),
            "|",
            ("owner_id", "=", user.id),
            ("member_ids.partner_id", "=", user.partner_id.id),
        ]

    # -------------------------------------------------------------------------
    # COMPUTE: FAVORITES
    # -------------------------------------------------------------------------

    @api.depends("favorite_user_ids")
    @api.depends_context("uid")
    def _compute_is_favorite(self):
        favorite_articles = self.filtered(
            lambda a: self.env.user in a.favorite_user_ids
        )
        for article in self:
            article.is_favorite = article in favorite_articles

    def _inverse_is_favorite(self):
        to_favorite = self.filtered(lambda a: a.is_favorite)
        to_unfavorite = self - to_favorite
        to_favorite.sudo().write(
            {"favorite_user_ids": [Command.link(self.env.uid)]}
        )
        to_unfavorite.sudo().write(
            {"favorite_user_ids": [Command.unlink(self.env.uid)]}
        )

    def _search_is_favorite(self, operator, value):
        if (operator == "=" and value) or (operator == "!=" and not value):
            return [("favorite_user_ids", "in", [self.env.uid])]
        return [("favorite_user_ids", "not in", [self.env.uid])]

    def toggle_favorite(self):
        """Toggle favorite status for the current user."""
        for article in self:
            if self.env.user in article.favorite_user_ids:
                article.sudo().write(
                    {"favorite_user_ids": [Command.unlink(self.env.uid)]}
                )
            else:
                article.sudo().write(
                    {"favorite_user_ids": [Command.link(self.env.uid)]}
                )

    # -------------------------------------------------------------------------
    # ACTIONS: LOCK / UNLOCK
    # -------------------------------------------------------------------------

    def action_toggle_lock(self):
        self.ensure_one()
        if self.is_locked:
            if (
                self.locked_by != self.env.user
                and not self.user_has_admin_access
            ):
                raise UserError(
                    _(
                        "Only the user who locked this article or an admin can unlock it."
                    )
                )
            self.write({"is_locked": False, "locked_by": False})
        else:
            self.write({"is_locked": True, "locked_by": self.env.uid})

    # -------------------------------------------------------------------------
    # ACTIONS: TRASH / RESTORE
    # -------------------------------------------------------------------------

    def action_send_to_trash(self):
        """Move article and its descendants to trash."""
        now = fields.Datetime.now()
        # Only trash root-level selected articles; children cascade
        for article in self:
            all_descendants = self.search(
                [("parent_path", "like", f"{article.parent_path}%")]
            )
            all_descendants.write({"is_trashed": True, "trashed_date": now})

    def action_restore_from_trash(self):
        """Restore article from trash. If parent is trashed, move to root."""
        for article in self:
            vals = {"is_trashed": False, "trashed_date": False}
            if article.parent_id.is_trashed:
                vals["parent_id"] = False
            article.write(vals)

    @api.model
    def _cron_empty_trash(self):
        """Permanently delete articles trashed > 30 days ago."""
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=30)
        trashed = self.search(
            [("is_trashed", "=", True), ("trashed_date", "<", cutoff)]
        )
        if trashed:
            _logger.info(
                "Knowledge: permanently deleting %d trashed articles",
                len(trashed),
            )
            trashed.with_context(force_unlink=True).unlink()

    # -------------------------------------------------------------------------
    # ACTIONS: TEMPLATES
    # -------------------------------------------------------------------------

    def action_create_from_template(self):
        """Create a new article from this template."""
        self.ensure_one()
        if not self.is_template:
            raise UserError(_("This article is not a template."))
        new_article = self.copy(
            {
                "is_template": False,
                "name": self.name,
                "category": "private",
                "owner_id": self.env.uid,
                "parent_id": False,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "knowledge.article",
            "res_id": new_article.id,
            "view_mode": "form",
            "target": "current",
        }

    # -------------------------------------------------------------------------
    # ACTIONS: MOVE
    # -------------------------------------------------------------------------

    def action_move_to(self, parent_id=False, before_article_id=False):
        """Move article under a new parent, optionally before a sibling."""
        self.ensure_one()
        vals = {"parent_id": parent_id}

        if parent_id:
            parent = self.browse(parent_id)
            vals["category"] = parent.category

        if before_article_id:
            before = self.browse(before_article_id)
            vals["sequence"] = before.sequence
            # Shift siblings after this one
            siblings = self.search(
                [
                    ("parent_id", "=", parent_id),
                    ("sequence", ">=", before.sequence),
                    ("id", "!=", self.id),
                ]
            )
            for sibling in siblings:
                sibling.sequence += 1
        self.write(vals)

    # -------------------------------------------------------------------------
    # ACTIONS: VERSION HISTORY
    # -------------------------------------------------------------------------

    def action_restore_version(self, field_name, revision_id):
        """Restore body content to a previous version."""
        self.ensure_one()
        restored_content = self.html_field_history_get_content_at_revision(
            field_name, revision_id
        )
        self.write({field_name: restored_content})

    # -------------------------------------------------------------------------
    # SIDEBAR DATA
    # -------------------------------------------------------------------------

    @api.model
    def get_sidebar_articles(self, active_article_id=False):
        """Return structured data for the sidebar tree."""
        user = self.env.user
        domain_base = [("is_trashed", "=", False), ("is_template", "=", False)]

        workspace_roots = self.search(
            domain_base
            + [("category", "=", "workspace"), ("parent_id", "=", False)],
            order="name, id",
        )
        private_roots = self.search(
            domain_base
            + [
                ("category", "=", "private"),
                ("parent_id", "=", False),
                ("owner_id", "=", user.id),
            ],
            order="name, id",
        )
        # Articles shared directly with the user (any category, not owned by user)
        shared_with_me_roots = self.search(
            domain_base
            + [
                ("parent_id", "=", False),
                ("owner_id", "!=", user.id),
                ("member_ids.partner_id", "=", user.partner_id.id),
            ],
            order="name, id",
        )
        favorites = self.search(
            domain_base + [("favorite_user_ids", "in", [user.id])],
            order="name, id",
        )

        # Determine which articles to expand (ancestors of active article)
        expanded_ids = set()
        if active_article_id:
            article = self.browse(active_article_id).exists()
            if article and article.parent_path:
                expanded_ids = {
                    int(x)
                    for x in article.parent_path.split("/")
                    if x
                }

        def _article_to_dict(article, depth=0):
            children = article.child_ids.filtered(
                lambda c: not c.is_trashed and not c.is_template
            ).sorted(lambda c: (c.name or "").lower())
            return {
                "type": "article",
                "id": article.id,
                "name": article.name,
                "icon": article.icon or "",
                "has_children": bool(children),
                "is_favorite": user in article.favorite_user_ids,
                "category": article.category,
                "knowledge_category_id": article.knowledge_category_id.id or False,
                "children": (
                    [_article_to_dict(c, depth + 1) for c in children]
                    if article.id in expanded_ids or depth == 0
                    else []
                ),
                "is_expanded": article.id in expanded_ids,
            }

        def _article_to_dict_shared_with_me(article):
            member = article.member_ids.filtered(
                lambda m: m.partner_id == user.partner_id
            )
            return {
                "type": "article",
                "id": article.id,
                "name": article.name,
                "icon": article.icon or "",
                "has_children": False,
                "category": article.category,
                "knowledge_category_id": article.knowledge_category_id.id or False,
                "member_id": member[0].id if member else False,
            }

        # Build Shared section: category folder nodes + uncategorized articles
        def _category_to_dict(cat):
            cat_articles = self.search(
                domain_base + [
                    ("category", "=", "shared"),
                    ("knowledge_category_id", "=", cat.id),
                    ("parent_id", "=", False),
                ],
                order="name, id",
            )
            sub_cats = self.env["knowledge.category"].search(
                [("parent_id", "=", cat.id)], order="name"
            )
            return {
                "type": "category",
                "id": cat.id,
                "name": cat.name,
                "is_expanded": False,
                "children": (
                    [_category_to_dict(c) for c in sub_cats]
                    + [_article_to_dict(a) for a in cat_articles]
                ),
            }

        root_categories = self.env["knowledge.category"].search(
            [("parent_id", "=", False)], order="name"
        )
        shared_uncategorized = self.search(
            domain_base + [
                ("category", "=", "shared"),
                ("parent_id", "=", False),
                ("knowledge_category_id", "=", False),
            ],
            order="name, id",
        )
        shared_data = (
            [_category_to_dict(c) for c in root_categories]
            + [_article_to_dict(a) for a in shared_uncategorized]
        )

        return {
            "workspace": [_article_to_dict(a) for a in workspace_roots],
            "shared": shared_data,
            "private": [_article_to_dict(a) for a in private_roots],
            "shared_with_me": [
                _article_to_dict_shared_with_me(a) for a in shared_with_me_roots
            ],
            "favorites": [
                {"id": a.id, "name": a.name, "icon": a.icon or ""}
                for a in favorites
            ],
            "trash_count": self.search_count(
                [("is_trashed", "=", True)]
            ),
        }

    @api.model
    def search_articles(self, query, limit=20):
        """Return a flat list of articles matching ``query`` by title.

        Results are scoped to what the current user may access (``search``
        applies record rules) and carry a breadcrumb describing where each
        article lives, e.g. ``Shared › Finance ›``.
        """
        if not query or not query.strip():
            return []

        articles = self.search(
            [
                ("is_trashed", "=", False),
                ("is_template", "=", False),
                ("name", "ilike", query.strip()),
            ],
            order="name",
            limit=limit,
        )
        if not articles:
            return []

        # Batch-load ancestor names (one browse) to avoid N+1 queries.
        ancestor_ids = set()
        for article in articles:
            if article.parent_path:
                ancestor_ids.update(
                    int(x)
                    for x in article.parent_path.split("/")
                    if x and int(x) != article.id
                )
        name_by_id = {
            a.id: a.name
            for a in self.browse(list(ancestor_ids))
        }

        section_labels = {
            "workspace": "Workspace",
            "shared": "Shared",
            "private": "My Articles",
        }

        results = []
        for article in articles:
            parts = [section_labels.get(article.category, article.category or "")]
            if article.knowledge_category_id:
                parts.append(article.knowledge_category_id.name)
            if article.parent_path:
                for x in article.parent_path.split("/"):
                    if x and int(x) != article.id:
                        parts.append(name_by_id.get(int(x), ""))
            parts = [p for p in parts if p]
            breadcrumb = (" › ".join(parts) + " ›") if parts else ""
            results.append({
                "id": article.id,
                "name": article.name,
                "icon": article.icon or "",
                "breadcrumb": breadcrumb,
            })
        return results

    def get_article_children(self):
        """Lazy-load children for sidebar tree expansion."""
        self.ensure_one()
        children = self.child_ids.filtered(
            lambda c: not c.is_trashed and not c.is_template
        ).sorted(lambda c: (c.name or "").lower())
        return [
            {
                "id": c.id,
                "name": c.name,
                "icon": c.icon or "",
                "has_children": bool(c.child_ids),
                "category": c.category,
                "children": [],
                "is_expanded": False,
            }
            for c in children
        ]

    # -------------------------------------------------------------------------
    # INTEGRATION: attachment_zipped_download mixin
    # -------------------------------------------------------------------------

    def _get_downloadable_attachments(self):
        """Override from ir.attachment.action_download mixin."""
        return self.env["ir.attachment"].search(
            [
                ("res_model", "=", self._name),
                ("res_id", "in", self.ids),
                ("type", "=", "binary"),
            ]
        )

    # -------------------------------------------------------------------------
    # CRUD OVERRIDES
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Inherit category from parent if not explicitly set
            if vals.get("parent_id") and "category" not in vals:
                parent = self.browse(vals["parent_id"])
                vals["category"] = parent.category
            # Default owner to current user
            if "owner_id" not in vals:
                vals["owner_id"] = self.env.uid
        return super().create(vals_list)

    def write(self, vals):
        # Lock enforcement
        if self._should_check_lock(vals):
            for article in self:
                if article.is_locked and article.locked_by != self.env.user:
                    if not self.env.user.has_group(
                        "knowledge.group_knowledge_manager"
                    ):
                        raise UserError(
                            _(
                                'Article "%(name)s" is locked by %(user)s.',
                                name=article.name,
                                user=article.locked_by.name,
                            )
                        )
        # Admin-only fields: membership and ownership transfer
        admin_only_fields = {"member_ids", "owner_id"}
        if admin_only_fields.intersection(vals.keys()):
            for article in self:
                if not article.user_has_admin_access:
                    raise AccessError(
                        _(
                            "You need admin permission to change access settings on this article."
                        )
                    )
        # Owner-or-admin fields: moving between sections / categories
        move_fields = {"category", "knowledge_category_id", "parent_id"}
        if move_fields.intersection(vals.keys()):
            for article in self:
                if not article.user_has_admin_access and article.owner_id != self.env.user:
                    raise AccessError(
                        _(
                            "Only the article owner or an admin can move this article."
                        )
                    )
        return super().write(vals)

    def _should_check_lock(self, vals):
        """Determine if the write operation should be lock-checked."""
        # Lock/unlock operations bypass the lock check
        lock_fields = {"is_locked", "locked_by"}
        if lock_fields.issuperset(vals.keys()):
            return False
        # Favorite toggle bypasses lock
        if set(vals.keys()) == {"favorite_user_ids"}:
            return False
        # Trash operations bypass lock
        if set(vals.keys()) <= {"is_trashed", "trashed_date", "active"}:
            return False
        return True

    def unlink(self):
        if not self.env.context.get("force_unlink"):
            for article in self:
                if not article.user_has_admin_access and article.owner_id != self.env.user:
                    raise AccessError(
                        _(
                            "Only the article owner or an admin can delete this article."
                        )
                    )
        return super().unlink()

    def copy(self, default=None):
        default = dict(default or {})
        default.setdefault("name", _("%s (copy)", self.name))
        default.setdefault("is_locked", False)
        default.setdefault("locked_by", False)
        default.setdefault("is_trashed", False)
        default.setdefault("trashed_date", False)
        default.setdefault("favorite_user_ids", [Command.clear()])
        default.setdefault("member_ids", [Command.clear()])
        return super().copy(default)
