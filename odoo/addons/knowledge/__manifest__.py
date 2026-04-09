{
    "name": "Knowledge",
    "version": "19.0.1.0.0",
    "category": "Knowledge",
    "summary": "Knowledge base with hierarchical articles, sharing, and collaboration",
    "description": """
Knowledge Management
====================
Provides a full-featured knowledge base with:
- Hierarchical articles with rich HTML editing
- Workspace / Shared / Private organization
- Per-article member-based permissions
- Favorites, templates, version history
- Lock/unlock, archive, trash/restore workflows
- Structured items with custom properties
- Integrates with document_url for URL attachments
- Integrates with attachment_zipped_download for bulk export
    """,
    "author": "Sage-ERP",
    "website": "",
    "license": "LGPL-3",
    "depends": [
        "document_knowledge",
        "document_page",
        "mail",
        "html_editor",
        "document_url",
        "attachment_zipped_download",
    ],
    "data": [
        "security/knowledge_security.xml",
        "security/ir.model.access.csv",
        "wizard/knowledge_article_share_views.xml",
        "views/knowledge_article_views.xml",
        "views/knowledge_category_views.xml",
        "views/knowledge_menus.xml",
        "views/res_config_settings_views.xml",
        "data/knowledge_data.xml",
        "data/knowledge_templates.xml",
    ],
    "demo": [
        "demo/knowledge_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "knowledge/static/src/scss/knowledge.scss",
            "knowledge/static/src/js/emoji_picker.js",
            "knowledge/static/src/xml/emoji_picker.xml",
            "knowledge/static/src/js/knowledge_icon_widget.js",
            "knowledge/static/src/js/knowledge_client_action.js",
            "knowledge/static/src/xml/knowledge_client_action.xml",
        ],
    },
    "installable": True,
    "application": False,
}
