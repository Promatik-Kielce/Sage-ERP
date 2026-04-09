from odoo import http
from odoo.http import request


class KnowledgeController(http.Controller):

    @http.route("/knowledge/sidebar", type="json", auth="user")
    def get_sidebar_data(self, active_article_id=False):
        """Return sidebar tree data for the Knowledge client action."""
        return (
            request.env["knowledge.article"]
            .get_sidebar_articles(active_article_id=active_article_id)
        )

    @http.route("/knowledge/article/children", type="json", auth="user")
    def get_article_children(self, article_id):
        """Lazy-load children for a sidebar tree node."""
        article = request.env["knowledge.article"].browse(int(article_id))
        if not article.exists():
            return []
        return article.get_article_children()

    @http.route("/knowledge/article/data", type="json", auth="user")
    def get_article_data(self, article_id):
        """Load full article data for the content area."""
        article = request.env["knowledge.article"].browse(int(article_id))
        if not article.exists():
            return False
        return {
            "id": article.id,
            "name": article.name,
            "icon": article.icon or "",
            "body": article.body or "",
            "cover_image": article.cover_image,
            "full_width": article.full_width,
            "category": article.category,
            "is_favorite": request.env.user in article.favorite_user_ids,
            "is_locked": article.is_locked,
            "locked_by": (
                {"id": article.locked_by.id, "name": article.locked_by.name}
                if article.locked_by
                else False
            ),
            "is_trashed": article.is_trashed,
            "is_template": article.is_template,
            "owner_id": article.owner_id.id,
            "owner_name": article.owner_id.name,
            "user_permission": article.user_permission,
            "user_has_write_access": article.user_has_write_access,
            "parent_id": article.parent_id.id if article.parent_id else False,
            "parent_name": article.parent_id.name if article.parent_id else "",
            "has_children": bool(article.child_ids),
            "member_count": len(article.member_ids),
            "message_count": article.message_count,
            "pdf_attachments": [
                {"id": a.id, "name": a.name}
                for a in request.env["ir.attachment"].search([
                    ("res_model", "=", "knowledge.article"),
                    ("res_id", "=", article.id),
                    ("mimetype", "=", "application/pdf"),
                ])
            ],
        }

    @http.route("/knowledge/article/toggle_favorite", type="json", auth="user")
    def toggle_favorite(self, article_id):
        """Toggle favorite status for the current user."""
        article = request.env["knowledge.article"].browse(int(article_id))
        article.toggle_favorite()
        return {"is_favorite": request.env.user in article.favorite_user_ids}

    @http.route("/knowledge/article/toggle_lock", type="json", auth="user")
    def toggle_lock(self, article_id):
        """Toggle lock status."""
        article = request.env["knowledge.article"].browse(int(article_id))
        article.action_toggle_lock()
        return {
            "is_locked": article.is_locked,
            "locked_by": (
                {"id": article.locked_by.id, "name": article.locked_by.name}
                if article.locked_by
                else False
            ),
        }

    @http.route("/knowledge/article/save", type="json", auth="user")
    def save_article(self, article_id, vals):
        """Save article content (debounced from frontend)."""
        article = request.env["knowledge.article"].browse(int(article_id))
        allowed_fields = {"name", "body", "icon", "full_width"}
        safe_vals = {k: v for k, v in vals.items() if k in allowed_fields}
        if safe_vals:
            article.write(safe_vals)
        return True

    # --- Move article to section / category (drag-and-drop) ---

    @http.route("/knowledge/article/move_to_section", type="json", auth="user")
    def move_to_section(self, article_id, category, knowledge_category_id=False):
        """Change article section and/or shared category (called from DnD)."""
        article = request.env["knowledge.article"].browse(int(article_id))
        if not article.exists():
            return False
        vals = {"category": category}
        if knowledge_category_id:
            vals["knowledge_category_id"] = int(knowledge_category_id)
        else:
            vals["knowledge_category_id"] = False
        article.write(vals)
        return True

    # --- Remove self from article member list ---

    @http.route("/knowledge/article/remove_member", type="json", auth="user")
    def remove_member(self, member_id):
        """Remove the current user's membership from a shared article."""
        member = request.env["knowledge.article.member"].browse(int(member_id))
        if member.exists() and member.partner_id == request.env.user.partner_id:
            member.unlink()
        return True

    # --- PDF endpoints ---

    @http.route("/knowledge/article/upload_pdf", type="json", auth="user")
    def upload_pdf(self, article_id, file_name, file_data):
        """Upload a PDF and attach it to the article."""
        article = request.env["knowledge.article"].browse(int(article_id))
        if not article.exists():
            return False
        attachment = request.env["ir.attachment"].create({
            "name": file_name,
            "datas": file_data,
            "res_model": "knowledge.article",
            "res_id": article.id,
            "mimetype": "application/pdf",
        })
        return {"id": attachment.id, "name": attachment.name}

    @http.route("/knowledge/article/delete_pdf", type="json", auth="user")
    def delete_pdf(self, attachment_id):
        """Delete a PDF attachment."""
        attachment = request.env["ir.attachment"].browse(int(attachment_id))
        if attachment.exists():
            attachment.unlink()
        return True

    @http.route("/knowledge/article/convert_pdf", type="json", auth="user")
    def convert_pdf_to_article(self, article_id, attachment_id):
        """Extract text from PDF and append to article body."""
        import base64
        import io
        import logging

        _logger = logging.getLogger(__name__)

        attachment = request.env["ir.attachment"].browse(int(attachment_id))
        if not attachment.exists():
            return {"error": "Attachment not found"}

        article = request.env["knowledge.article"].browse(int(article_id))
        if not article.exists():
            return {"error": "Article not found"}

        try:
            from PyPDF2 import PdfReader
        except ImportError:
            try:
                from pypdf import PdfReader
            except ImportError:
                _logger.warning("PDF conversion requires PyPDF2 or pypdf library")
                return {"error": "PDF conversion library not installed. Install with: pip install pypdf"}

        try:
            pdf_bytes = base64.b64decode(attachment.datas)
            reader = PdfReader(io.BytesIO(pdf_bytes))
            html_parts = [f"<h2>{attachment.name}</h2>"]
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    paragraphs = text.split("\n\n")
                    for p in paragraphs:
                        cleaned = p.strip()
                        if cleaned:
                            html_parts.append(f"<p>{cleaned}</p>")
                    if i < len(reader.pages) - 1:
                        html_parts.append("<hr/>")
            new_body = (article.body or "") + "".join(html_parts)
            article.write({"body": new_body})
            return True
        except Exception as e:
            _logger.exception("Failed to convert PDF to article content")
            return {"error": str(e)}
