from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import KnowledgeTestCommon


@tagged("post_install", "-at_install")
class TestKnowledgeSecurity(KnowledgeTestCommon):

    def test_workspace_visible_to_knowledge_user(self):
        """Knowledge users can see workspace articles."""
        articles = (
            self.env["knowledge.article"]
            .with_user(self.knowledge_user)
            .search([("category", "=", "workspace")])
        )
        self.assertIn(self.workspace_article, articles)

    def test_private_not_visible_to_other_user(self):
        """Private articles are only visible to owner."""
        articles = (
            self.env["knowledge.article"]
            .with_user(self.knowledge_user)
            .search([("id", "=", self.private_article.id)])
        )
        self.assertFalse(articles)

    def test_private_visible_to_owner(self):
        """Private article visible to its owner."""
        # private_article was created by admin (default)
        articles = (
            self.env["knowledge.article"]
            .with_user(self.env.ref("base.user_admin"))
            .search([("id", "=", self.private_article.id)])
        )
        self.assertIn(self.private_article, articles)

    def test_shared_visible_to_member(self):
        """Shared articles visible to members."""
        # Add knowledge_user as member
        self.env["knowledge.article.member"].create(
            {
                "article_id": self.shared_article.id,
                "partner_id": self.knowledge_user.partner_id.id,
                "permission": "read",
            }
        )
        articles = (
            self.env["knowledge.article"]
            .with_user(self.knowledge_user)
            .search([("id", "=", self.shared_article.id)])
        )
        self.assertIn(self.shared_article, articles)

    def test_manager_sees_everything(self):
        """Knowledge managers can see all articles."""
        all_articles = (
            self.env["knowledge.article"]
            .with_user(self.knowledge_manager)
            .search([])
        )
        self.assertIn(self.workspace_article, all_articles)
        self.assertIn(self.private_article, all_articles)
        self.assertIn(self.shared_article, all_articles)

    def test_owner_permission(self):
        """Owner gets admin permission."""
        article = self.workspace_article.with_user(self.workspace_article.owner_id)
        self.assertEqual(article.user_permission, "admin")
        self.assertTrue(article.user_has_write_access)
        self.assertTrue(article.user_has_admin_access)

    def test_workspace_default_write_permission(self):
        """Knowledge users get write permission on workspace articles by default."""
        article = self.workspace_article.with_user(self.knowledge_user)
        self.assertEqual(article.user_permission, "write")
        self.assertTrue(article.user_has_write_access)
        self.assertFalse(article.user_has_admin_access)

    def test_member_permission_inheritance(self):
        """Member permission is inherited from parent article."""
        # Add knowledge_user as write member on workspace_article
        self.env["knowledge.article.member"].create(
            {
                "article_id": self.workspace_article.id,
                "partner_id": self.knowledge_user.partner_id.id,
                "permission": "write",
            }
        )
        # Child article should inherit write permission
        child = self.child_article.with_user(self.knowledge_user)
        self.assertEqual(child.user_permission, "write")

    def test_lock_prevents_write_by_non_holder(self):
        """Locked article cannot be written by non-lock holder."""
        self.workspace_article.action_toggle_lock()
        # Try to write as knowledge_user (not the lock holder)
        with self.assertRaises(Exception):
            self.workspace_article.with_user(self.knowledge_user).write(
                {"name": "Changed"}
            )

    def test_unlink_requires_admin(self):
        """Deleting article requires admin permission."""
        article = self.env["knowledge.article"].create(
            {
                "name": "To Delete",
                "category": "workspace",
            }
        )
        with self.assertRaises(AccessError):
            article.with_user(self.knowledge_user).unlink()
