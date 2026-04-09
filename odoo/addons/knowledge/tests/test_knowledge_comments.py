from odoo.tests import tagged
from .common import KnowledgeTestCommon


@tagged("post_install", "-at_install")
class TestKnowledgeComments(KnowledgeTestCommon):

    def test_read_only_member_can_post_comment(self):
        """Read-only member should be able to post a comment."""
        # Add knowledge_user as read-only member of private_article
        self.private_article.write({
            "member_ids": [(0, 0, {
                "partner_id": self.knowledge_user.partner_id.id,
                "permission": "read",
            })]
        })
        # As the read-only member, post a comment — must not raise
        self.private_article.with_user(self.knowledge_user).message_post(
            body="<p>A comment from a read-only user</p>",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        # Verify message was created
        comment = self.private_article.message_ids.filtered(
            lambda m: m.message_type == "comment"
        )
        self.assertEqual(len(comment), 1)
        self.assertIn("read-only", comment.body)

    def test_message_count_only_counts_user_comments(self):
        """message_count must exclude system notification messages."""
        article = self.env["knowledge.article"].create({
            "name": "Count Test Article",
            "category": "workspace",
            "body": "<p>body</p>",
        })
        initial_count = article.message_count
        # Post one user comment
        article.message_post(
            body="<p>user comment</p>",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        article.invalidate_recordset()
        self.assertEqual(article.message_count, initial_count + 1)

    def test_message_count_excludes_notifications(self):
        """Notification messages must not inflate message_count."""
        article = self.env["knowledge.article"].create({
            "name": "Notify Test",
            "category": "workspace",
            "body": "<p>body</p>",
        })
        initial_count = article.message_count
        # Post a system notification
        article.message_post(
            body="<p>system note</p>",
            message_type="notification",
        )
        article.invalidate_recordset()
        self.assertEqual(article.message_count, initial_count)
