# Knowledge Article Comments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collapsible right-side comments panel (full Odoo chatter) to the Knowledge module's custom client action, accessible to any user with at least read access to an article.

**Architecture:** Reuse Odoo's built-in `Chatter` OWL component — mount it in a 320 px drawer inside `knowledge.ClientAction`. Two backend changes: set `_mail_post_access = 'read'` so read-only members can post, and add a `message_count` computed field (filtering to user comments only) so the header button can display "Comments (N)". The controller's `/knowledge/article/data` endpoint exposes the count. No new files; no database migrations.

**Tech Stack:** Odoo 19 OWL framework, Python ORM (`mail.thread`), JSON-RPC controllers, Bootstrap 5 utility classes.

---

## File Map

| File | What changes |
|---|---|
| `odoo/addons/knowledge/models/knowledge_article.py` | Add `_mail_post_access`, `message_count` field, `_compute_message_count` |
| `odoo/addons/knowledge/controllers/main.py` | Add `"message_count"` to `get_article_data` response |
| `odoo/addons/knowledge/static/src/js/knowledge_client_action.js` | Import `Chatter`, register component, add `showComments` state, `toggleComments()` method, reset on navigation |
| `odoo/addons/knowledge/static/src/xml/knowledge_client_action.xml` | Wrap body in flex row, add Comments button to header, add comments panel with `<Chatter/>` |
| `odoo/addons/knowledge/tests/test_knowledge_comments.py` | New test file for backend changes |

---

## Task 1: Backend — model changes

**Files:**
- Modify: `odoo/addons/knowledge/models/knowledge_article.py`
- Create: `odoo/addons/knowledge/tests/test_knowledge_comments.py`

### Step 1.1 — Write the failing tests

Create `odoo/addons/knowledge/tests/test_knowledge_comments.py`:

```python
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
```

- [ ] **Step 1.2 — Run tests to verify they fail**

```bash
./odoo-bin -d test_db --test-tags=TestKnowledgeComments --stop-after-init 2>&1 | tail -30
```

Expected: errors such as `AttributeError: 'knowledge.article' object has no attribute 'message_count'` and `AccessError` on the permission test.

- [ ] **Step 1.3 — Add `_mail_post_access` and `message_count` to the model**

Open `odoo/addons/knowledge/models/knowledge_article.py`. Make two additions:

**A) After line 28 (`_check_company_auto = True`), add the class attribute:**

```python
    _mail_post_access = "read"
```

**B) After the `# === Multi-company ===` block (after `company_id` field, around line 156), add the computed field and method:**

```python
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
```

- [ ] **Step 1.4 — Run tests to verify they pass**

```bash
./odoo-bin -d test_db --test-tags=TestKnowledgeComments --stop-after-init 2>&1 | tail -30
```

Expected: `Ran 3 tests ... OK`

- [ ] **Step 1.5 — Commit**

```bash
git add odoo/addons/knowledge/models/knowledge_article.py \
        odoo/addons/knowledge/tests/test_knowledge_comments.py
git commit -m "feat(knowledge): allow read-only members to comment; add message_count field"
```

---

## Task 2: Controller — expose `message_count`

**Files:**
- Modify: `odoo/addons/knowledge/controllers/main.py:29-62`

The `get_article_data` method builds a dict returned to the frontend. Add `message_count` to it.

- [ ] **Step 2.1 — Add `message_count` to the controller response**

In `odoo/addons/knowledge/controllers/main.py`, find the `return {` block inside `get_article_data` (around line 29). Add one line after `"member_count"`:

```python
            "member_count": len(article.member_ids),
            "message_count": article.message_count,   # ← add this line
```

The full surrounding context for reference:

```python
            "has_children": bool(article.child_ids),
            "member_count": len(article.member_ids),
            "message_count": article.message_count,
            "pdf_attachments": [
```

- [ ] **Step 2.2 — Verify the tests still pass (regression)**

```bash
./odoo-bin -d test_db --test-tags=TestKnowledgeComments --stop-after-init 2>&1 | tail -10
```

Expected: `Ran 3 tests ... OK`

- [ ] **Step 2.3 — Commit**

```bash
git add odoo/addons/knowledge/controllers/main.py
git commit -m "feat(knowledge): expose message_count in article data endpoint"
```

---

## Task 3: Frontend JS — Chatter integration

**Files:**
- Modify: `odoo/addons/knowledge/static/src/js/knowledge_client_action.js`

Three changes: import, register, state + methods.

- [ ] **Step 3.1 — Import Chatter**

At the top of `knowledge_client_action.js`, after the existing imports (around line 13), add:

```javascript
import { Chatter } from "@mail/chatter/web_portal/chatter";
```

So the imports block looks like:

```javascript
import { Component, onWillStart, useState, markup, useRef, useEffect } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Wysiwyg } from "@html_editor/wysiwyg";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { HtmlViewer } from "@html_editor/components/html_viewer/html_viewer";
import { EmojiPicker } from "./emoji_picker";
import { Chatter } from "@mail/chatter/web_portal/chatter";
```

- [ ] **Step 3.2 — Register Chatter in `static components`**

Find line 129:

```javascript
    static components = { KnowledgeSidebarItem, KnowledgeCategoryItem, Wysiwyg, HtmlViewer, EmojiPicker };
```

Replace with:

```javascript
    static components = { KnowledgeSidebarItem, KnowledgeCategoryItem, Wysiwyg, HtmlViewer, EmojiPicker, Chatter };
```

- [ ] **Step 3.3 — Add `showComments` to state**

Find the `useState({` block (around line 139). Add `showComments: false` after `showIconPicker`:

```javascript
        this.state = useState({
            sidebar: {
                workspace: [],
                shared: [],
                private: [],
                shared_with_me: [],
                favorites: [],
                trash_count: 0,
            },
            activeArticle: null,
            loading: true,
            saving: false,
            sidebarCollapsed: false,
            showIconPicker: false,
            showComments: false,
        });
```

- [ ] **Step 3.4 — Reset `showComments` and set `message_count` on navigation**

Find `onSelectArticle` (around line 224). Add `this.state.showComments = false;` immediately before the RPC call:

```javascript
    async onSelectArticle(articleId) {
        if (this._saveTimeout) {
            clearTimeout(this._saveTimeout);
            this._saveTimeout = null;
            if (this.editor && this.state.activeArticle) {
                await this._saveArticle({ body: this.editor.getContent() });
            }
        }
        this.editor = null;
        this.state.showComments = false;   // ← add this line
        const data = await rpc("/knowledge/article/data", {
            article_id: articleId,
        });
        if (data) {
            this.state.activeArticle = data;
        }
    }
```

- [ ] **Step 3.5 — Add `toggleComments` method**

Add the method after `toggleSidebar` (around line 401):

```javascript
    toggleComments() {
        this.state.showComments = !this.state.showComments;
    }
```

- [ ] **Step 3.6 — Commit**

```bash
git add odoo/addons/knowledge/static/src/js/knowledge_client_action.js
git commit -m "feat(knowledge): wire Chatter component into client action JS"
```

---

## Task 4: Frontend XML — toggle button and comments panel

**Files:**
- Modify: `odoo/addons/knowledge/static/src/xml/knowledge_client_action.xml`

Two changes: add the button to the header, and add the panel + restructure the content area.

- [ ] **Step 4.1 — Add the "Comments (N)" button to the content header**

Find the `<div t-if="state.activeArticle" class="d-flex gap-1">` block in the content header (around line 303). It currently ends with the "Open full form" button. Add the Comments button **before** that last button:

```xml
                    <div t-if="state.activeArticle" class="d-flex gap-1">
                        <span t-if="state.saving" class="text-muted small me-2">
                            <i class="fa fa-spinner fa-spin"/> Saving...
                        </span>
                        <button class="btn btn-sm"
                                title="Toggle favorite"
                                t-att-class="state.activeArticle.is_favorite ? 'btn-warning' : 'btn-outline-secondary'"
                                t-on-click="onToggleFavorite">
                            <i class="fa fa-star"/>
                        </button>
                        <button class="btn btn-sm"
                                t-att-class="state.activeArticle.is_locked ? 'btn-danger' : 'btn-outline-secondary'"
                                title="Toggle lock"
                                t-on-click="onToggleLock">
                            <i t-att-class="state.activeArticle.is_locked ? 'fa fa-lock' : 'fa fa-unlock-alt'"/>
                        </button>
                        <button class="btn btn-sm btn-outline-secondary"
                                title="Attach PDF"
                                t-on-click="onUploadPdf">
                            <i class="fa fa-file-pdf-o"/>
                        </button>
                        <button class="btn btn-sm btn-outline-secondary"
                                title="Share article"
                                t-on-click="onShareArticle">
                            <i class="fa fa-share-alt"/>
                        </button>
                        <button class="btn btn-sm btn-outline-secondary"
                                title="Add sub-article"
                                t-on-click="onCreateChildArticle">
                            <i class="fa fa-plus"/>
                        </button>
                        <button class="btn btn-sm"
                                t-att-class="state.showComments ? 'btn-secondary' : 'btn-outline-secondary'"
                                title="Toggle comments panel"
                                t-on-click="toggleComments">
                            <i class="fa fa-comments me-1"/>
                            Comments (<t t-out="state.activeArticle.message_count || 0"/>)
                        </button>
                        <button class="btn btn-sm btn-outline-secondary"
                                title="Open full form"
                                t-on-click="onOpenForm">
                            <i class="fa fa-external-link"/>
                        </button>
                    </div>
```

- [ ] **Step 4.2 — Wrap the content body in a flex row and add the comments panel**

Find the `<!-- Content Body -->` div (around line 343):

```xml
                <!-- Content Body -->
                <div class="o_knowledge_content_body flex-grow-1 overflow-auto">
```

Wrap everything from that opening tag through its closing `</div>` (the one that closes the content area before the outer `</div>`) in a new wrapper div, and add the comments panel as a sibling. The new structure is:

```xml
                <!-- Content Body + Comments Panel -->
                <div class="o_knowledge_content_with_panel d-flex flex-grow-1 overflow-hidden">

                    <!-- Content Body -->
                    <div class="o_knowledge_content_body flex-grow-1 overflow-auto">
                        <!-- (all existing content body markup stays here unchanged) -->
                    </div>

                    <!-- Comments Panel (right drawer) -->
                    <div t-if="state.showComments"
                         class="o_knowledge_comments_panel border-start d-flex flex-column overflow-hidden"
                         style="width: 320px; min-width: 320px;">
                        <div class="o_knowledge_comments_header border-bottom px-3 py-2 d-flex align-items-center justify-content-between flex-shrink-0">
                            <strong>Comments</strong>
                            <button class="btn btn-sm btn-link p-0 text-muted"
                                    t-on-click="toggleComments">
                                <i class="fa fa-times"/>
                            </button>
                        </div>
                        <div class="flex-grow-1 overflow-auto">
                            <Chatter
                                threadModel="'knowledge.article'"
                                threadId="state.activeArticle.id"
                                composer="!state.activeArticle.is_trashed"
                                isChatterAside="true"/>
                        </div>
                    </div>

                </div><!-- /.o_knowledge_content_with_panel -->
```

**Important:** The existing `<div class="o_knowledge_content_body flex-grow-1 overflow-auto">` opening tag and its entire contents (loading spinner, article view, PDF section, empty state) remain exactly as they are — you are only adding a wrapper div around the body div and adding the panel as a sibling after it.

- [ ] **Step 4.3 — Update the module to load changes**

```bash
./odoo-bin -d your_db -u knowledge --stop-after-init 2>&1 | tail -20
```

Expected: module updates without errors.

- [ ] **Step 4.4 — Commit**

```bash
git add odoo/addons/knowledge/static/src/xml/knowledge_client_action.xml
git commit -m "feat(knowledge): add collapsible comments panel with full chatter to client action"
```

---

## Task 5: Register test file in `__init__.py`

**Files:**
- Modify: `odoo/addons/knowledge/tests/__init__.py`

- [ ] **Step 5.1 — Add the new test module**

Open `odoo/addons/knowledge/tests/__init__.py` and add the import:

```python
from . import test_knowledge_comments
```

- [ ] **Step 5.2 — Run all knowledge tests (regression)**

```bash
./odoo-bin -d test_db --test-tags=knowledge --stop-after-init 2>&1 | tail -20
```

Expected: all tests pass with no errors.

- [ ] **Step 5.3 — Commit**

```bash
git add odoo/addons/knowledge/tests/__init__.py
git commit -m "test(knowledge): register test_knowledge_comments in test suite"
```

---

## Task 6: End-to-end manual verification

Start Odoo with dev mode:

```bash
./odoo-bin -d your_db --addons-path=addons,odoo/addons --dev=all
```

- [ ] Open Knowledge via the top menu → select any article.
- [ ] Confirm **"Comments (0)"** button appears in the content header toolbar.
- [ ] Click the button → right panel (320 px) slides in with the Odoo chatter.
- [ ] Post a comment → verify it appears in the panel immediately.
- [ ] Confirm the button now shows **"Comments (1)"**.
- [ ] Navigate to a different article → panel closes, count resets to that article's count.
- [ ] Log in as a user with **read-only** membership on a private article → confirm Comments button is visible and they can post.
- [ ] Open a **trashed** article → confirm chatter is visible but the message composer is absent.
- [ ] Open the same article via **"Open full form"** (external link button) → confirm the standard form view chatter still works (regression check).
- [ ] Click the **×** button inside the panel → panel closes.
- [ ] Toggle Comments button again → panel re-opens on the same article.
