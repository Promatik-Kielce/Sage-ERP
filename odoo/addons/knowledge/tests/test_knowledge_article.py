from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import KnowledgeTestCommon


@tagged("post_install", "-at_install")
class TestKnowledgeArticle(KnowledgeTestCommon):

    def test_article_creation(self):
        """Test basic article creation."""
        article = self.env["knowledge.article"].create(
            {
                "name": "Test Article",
                "category": "private",
                "body": "<p>Hello World</p>",
            }
        )
        self.assertEqual(article.name, "Test Article")
        self.assertEqual(article.category, "private")
        self.assertEqual(article.owner_id, self.env.user)
        self.assertFalse(article.is_trashed)
        self.assertFalse(article.is_locked)

    def test_article_hierarchy(self):
        """Test parent/child relationships."""
        self.assertEqual(self.child_article.parent_id, self.workspace_article)
        self.assertIn(self.child_article, self.workspace_article.child_ids)
        # Child inherits category from parent
        self.assertEqual(self.child_article.category, "workspace")

    def test_article_hierarchy_cycle_prevention(self):
        """Test that circular parent references are prevented."""
        with self.assertRaises(ValidationError):
            self.workspace_article.parent_id = self.child_article.id

    def test_article_favorite(self):
        """Test favorite toggling."""
        self.assertFalse(self.workspace_article.is_favorite)
        self.workspace_article.toggle_favorite()
        self.assertTrue(
            self.env.user in self.workspace_article.favorite_user_ids
        )

    def test_article_lock(self):
        """Test lock/unlock behavior."""
        self.workspace_article.action_toggle_lock()
        self.assertTrue(self.workspace_article.is_locked)
        self.assertEqual(self.workspace_article.locked_by, self.env.user)

        self.workspace_article.action_toggle_lock()
        self.assertFalse(self.workspace_article.is_locked)
        self.assertFalse(self.workspace_article.locked_by)

    def test_article_trash(self):
        """Test trash and restore."""
        self.workspace_article.action_send_to_trash()
        self.assertTrue(self.workspace_article.is_trashed)
        self.assertTrue(self.workspace_article.trashed_date)
        # Child should also be trashed
        self.assertTrue(self.child_article.is_trashed)

        # Restore the child (parent is still trashed, so child moves to root)
        self.child_article.action_restore_from_trash()
        self.assertFalse(self.child_article.is_trashed)
        self.assertFalse(self.child_article.parent_id)

    def test_article_copy(self):
        """Test article duplication."""
        copy = self.workspace_article.copy()
        self.assertIn("(copy)", copy.name)
        self.assertFalse(copy.is_locked)
        self.assertFalse(copy.is_trashed)
        self.assertFalse(copy.favorite_user_ids)
        self.assertFalse(copy.member_ids)

    def test_article_template(self):
        """Test template creation."""
        template = self.env["knowledge.article"].create(
            {
                "name": "Test Template",
                "is_template": True,
                "category": "workspace",
                "body": "<p>Template content</p>",
            }
        )
        result = template.action_create_from_template()
        new_article = self.env["knowledge.article"].browse(result["res_id"])
        self.assertEqual(new_article.name, "Test Template")
        self.assertFalse(new_article.is_template)
        self.assertEqual(new_article.category, "private")

    def test_article_not_template_error(self):
        """Test that non-template articles cannot be used as template."""
        with self.assertRaises(UserError):
            self.workspace_article.action_create_from_template()

    def test_article_move(self):
        """Test moving article to different parent."""
        new_parent = self.env["knowledge.article"].create(
            {
                "name": "New Parent",
                "category": "workspace",
            }
        )
        self.child_article.action_move_to(parent_id=new_parent.id)
        self.assertEqual(self.child_article.parent_id, new_parent)

    def test_sidebar_data(self):
        """Test sidebar data generation."""
        data = self.env["knowledge.article"].get_sidebar_articles()
        self.assertIn("workspace", data)
        self.assertIn("shared", data)
        self.assertIn("private", data)
        self.assertIn("favorites", data)
        self.assertIn("trash_count", data)
        # Workspace root should appear
        workspace_ids = [a["id"] for a in data["workspace"]]
        self.assertIn(self.workspace_article.id, workspace_ids)

    def test_article_version_history(self):
        """Test that version history is recorded on body change."""
        article = self.env["knowledge.article"].create(
            {
                "name": "Versioned Article",
                "body": "<p>Version 1</p>",
            }
        )
        article.write({"body": "<p>Version 2</p>"})
        self.assertTrue(article.html_field_history)
        self.assertIn("body", article.html_field_history)

    def test_members(self):
        """Test member creation."""
        partner = self.knowledge_user.partner_id
        self.env["knowledge.article.member"].create(
            {
                "article_id": self.shared_article.id,
                "partner_id": partner.id,
                "permission": "write",
            }
        )
        self.assertEqual(len(self.shared_article.member_ids), 1)
        self.assertEqual(
            self.shared_article.member_ids[0].permission, "write"
        )
