from odoo.tests.common import TransactionCase


class KnowledgeTestCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create test users
        cls.knowledge_user = cls.env["res.users"].create(
            {
                "name": "Knowledge User",
                "login": "knowledge_user",
                "groups_id": [
                    (4, cls.env.ref("knowledge.group_knowledge_user").id),
                ],
            }
        )
        cls.knowledge_manager = cls.env["res.users"].create(
            {
                "name": "Knowledge Manager",
                "login": "knowledge_manager",
                "groups_id": [
                    (4, cls.env.ref("knowledge.group_knowledge_manager").id),
                ],
            }
        )
        cls.basic_user = cls.env["res.users"].create(
            {
                "name": "Basic User",
                "login": "basic_user",
                "groups_id": [
                    (4, cls.env.ref("base.group_user").id),
                ],
            }
        )

        # Create test articles
        cls.workspace_article = cls.env["knowledge.article"].create(
            {
                "name": "Workspace Root",
                "category": "workspace",
                "body": "<p>Workspace content</p>",
            }
        )
        cls.private_article = cls.env["knowledge.article"].create(
            {
                "name": "Private Article",
                "category": "private",
                "body": "<p>Private content</p>",
            }
        )
        cls.shared_article = cls.env["knowledge.article"].create(
            {
                "name": "Shared Article",
                "category": "shared",
                "body": "<p>Shared content</p>",
            }
        )
        cls.child_article = cls.env["knowledge.article"].create(
            {
                "name": "Child Article",
                "parent_id": cls.workspace_article.id,
                "body": "<p>Child content</p>",
            }
        )
