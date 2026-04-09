# Knowledge Article Comments — Design Spec

**Date:** 2026-04-09
**Branch:** knoweledge-module
**Status:** Approved

---

## Context

The Knowledge module has a custom OWL-based client action (`knowledge.ClientAction`) that renders articles in a sidebar + content layout. Users requested the ability to leave comments on articles. Any user who can read an article should be able to post a comment.

`knowledge.article` already inherits from `mail.thread` and `mail.activity.mixin`, so the full messaging infrastructure (messages, followers, reactions, attachments, @mentions) exists at the model level. The standard backend form view already has `<chatter/>`. The work is surfacing that capability in the custom client action UI.

---

## Goals

- Any user with at least **read** access to an article can post comments.
- Comments panel is a **collapsible right-side drawer** (320 px wide).
- Panel closes when navigating to a different article.
- A **"Comments (N)"** button in the content header shows the count and toggles the panel.
- Full chatter features: threaded replies, emoji reactions, file attachments, @mentions, activities.
- Reuse Odoo's built-in `Chatter` OWL component to minimise custom code.

---

## Architecture

### Backend — `odoo/addons/knowledge/models/knowledge_article.py`

**Change 1: Allow read-access users to post**

Add class attribute:
```python
_mail_post_access = 'read'
```

Default in `mail.thread` is `'write'`. This single line allows users with read-only member permission to call `message_post`.

**Change 2: Expose message count**

Add a non-stored computed field:
```python
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

This lets the frontend show "Comments (3)" without loading message records.

---

### Frontend — Client Action JS

**File:** `odoo/addons/knowledge/static/src/js/knowledge_client_action.js`

**Import Chatter:**
```javascript
import { Chatter } from "@mail/chatter/web_portal/chatter";
```

**Register component:**
```javascript
static components = { ..., Chatter };
```

**State additions:**
```javascript
showComments: false,
// message_count stored inside activeArticle object
```

**Reset on navigation** — in `onSelectArticle()`, reset before loading new article:
```javascript
this.state.showComments = false;
```

**Fetch `message_count`** — add `"message_count"` to the fields list in the article RPC read call.

**Toggle method:**
```javascript
toggleComments() {
    this.state.showComments = !this.state.showComments;
}
```

**Optimistic count increment** — after Chatter posts a message (using `hasParentReloadOnMessagePosted` prop or a custom callback), increment `state.activeArticle.message_count` locally.

---

### Frontend — Template

**File:** `odoo/addons/knowledge/static/src/xml/knowledge_client_action.xml`

**Layout change** — outer content area becomes a flex row:
```xml
<div class="o_knowledge_content flex-grow-1 d-flex flex-column overflow-hidden">
    <!-- existing header -->
    <div class="o_knowledge_content_with_panel d-flex flex-grow-1 overflow-hidden">
        <!-- existing content body (flex-grow-1) -->
        <!-- NEW: comments panel -->
    </div>
</div>
```

**Comments toggle button** — added to the content header action buttons:
```xml
<button class="btn btn-sm btn-outline-secondary"
        t-att-class="state.showComments ? 'btn-secondary' : 'btn-outline-secondary'"
        title="Toggle comments"
        t-on-click="toggleComments">
    <i class="fa fa-comments me-1"/>
    Comments (<t t-out="state.activeArticle.message_count || 0"/>)
</button>
```

**Comments panel:**
```xml
<div t-if="state.showComments"
     class="o_knowledge_comments_panel border-start d-flex flex-column overflow-auto"
     style="width: 320px; min-width: 320px;">
    <div class="o_knowledge_comments_header border-bottom px-3 py-2 d-flex align-items-center justify-content-between">
        <strong>Comments</strong>
        <button class="btn btn-sm btn-link p-0" t-on-click="toggleComments">
            <i class="fa fa-times"/>
        </button>
    </div>
    <Chatter
        threadModel="'knowledge.article'"
        threadId="state.activeArticle.id"
        composer="!state.activeArticle.is_trashed"
        isChatterAside="true"/>
</div>
```

---

## Security

| Scenario | Behaviour |
|---|---|
| User has `read` permission | Can view and post comments |
| User has `write` / `admin` permission | Can view and post comments |
| User has `none` permission | Article not loaded at all (record rule blocks it) |
| Article is trashed | Chatter visible but composer disabled (`composer="false"`) |
| Article is locked | Chatter fully functional (locking affects body editing only) |

---

## Files Changed

| File | Change |
|---|---|
| `odoo/addons/knowledge/models/knowledge_article.py` | Add `_mail_post_access`, `message_count` field + compute |
| `odoo/addons/knowledge/static/src/js/knowledge_client_action.js` | Import Chatter, state, toggle, fetch message_count |
| `odoo/addons/knowledge/static/src/xml/knowledge_client_action.xml` | Toggle button, panel layout, Chatter component |

No new files. No migrations needed (no schema change).

---

## Verification

1. Start Odoo: `./odoo-bin -d <db> --addons-path=addons,odoo/addons --dev=all`
2. Update the module: `./odoo-bin -d <db> -u knowledge --stop-after-init`
3. Open Knowledge via the menu → select any article.
4. Confirm "Comments (N)" button appears in the header.
5. Click it → right panel opens with full chatter.
6. Post a comment → count increments.
7. Navigate to another article → panel closes, count resets.
8. Log in as a user with only read access → confirm they can still post a comment.
9. Open a trashed article → confirm composer is disabled.
10. Verify chatter is still present in the standard form view (regression check).
