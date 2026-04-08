# Knowledge Article Icon Picker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw-text `icon` field input on `knowledge.article` with a click-to-open emoji picker popover (4 category tabs, ~80 emojis, remove button) in both the Knowledge OWL client action and the backend form view.

**Architecture:** A shared `EmojiPicker` OWL component holds all picker logic. It is used directly in `KnowledgeClientAction` for the OWL view, and wrapped by a custom `KnowledgeIconWidget` field widget for the backend form view. No backend changes are needed — the save and data routes already handle the `icon` field.

**Tech Stack:** OWL (Odoo 19 reactive UI), `@odoo/owl` (Component, useState, useEffect), `@web/core/network/rpc`, Odoo field widget registry (`@web/core/registry`), SCSS

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| **Create** | `knowledge/static/src/js/emoji_picker.js` | `EmojiPicker` OWL component — tabs, grid, remove |
| **Create** | `knowledge/static/src/xml/emoji_picker.xml` | Templates for `EmojiPicker` and `KnowledgeIconWidget` |
| **Create** | `knowledge/static/src/js/knowledge_icon_widget.js` | Odoo field widget wrapping `EmojiPicker` for form views |
| **Modify** | `knowledge/static/src/js/knowledge_client_action.js` | Add `showIconPicker` state, `onIconClick`, `onPickEmoji`, `onClosePicker`, click-outside handler |
| **Modify** | `knowledge/static/src/xml/knowledge_client_action.xml` | Make icon span clickable, add `EmojiPicker` conditional, add "+ icon" placeholder |
| **Modify** | `knowledge/static/src/scss/knowledge.scss` | Styles for picker popover, tabs, grid, remove button, icon trigger/placeholder |
| **Modify** | `knowledge/views/knowledge_article_views.xml` | Swap `<field name="icon">` for `<field name="icon" widget="knowledge_icon_picker"/>` |
| **Modify** | `knowledge/__manifest__.py` | Register 3 new assets in `web.assets_backend` |

---

## Task 1: Create the EmojiPicker OWL component

**Files:**
- Create: `knowledge/static/src/js/emoji_picker.js`
- Create: `knowledge/static/src/xml/emoji_picker.xml`

- [ ] **Step 1.1: Create `emoji_picker.js`**

```javascript
/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

export const EMOJI_CATEGORIES = [
    {
        label: "📄 Docs",
        emojis: [
            "📄","📁","📝","🗂️","📎","📊","🔑","🗒️","📋","📑",
            "🖊️","📰","📚","📒","📓","📔","📃","📜","🗃️","🗄️",
        ],
    },
    {
        label: "✅ Status",
        emojis: [
            "✅","❗","❓","🔒","🔓","⭐","🏷️","📌","🚩","⚠️",
            "🔔","💡","🎯","🔴","🟡","🟢","⏳","✔️","❌","🔁",
        ],
    },
    {
        label: "👤 People",
        emojis: [
            "👤","👥","🧑‍💼","👨‍💻","👩‍💻","🧑‍🏫","👨‍🔬","🤝","👋","🙋",
            "🧠","💬","📣","📢","🗣️","👁️","🫂","🤖","👑","🏆",
        ],
    },
    {
        label: "🔧 Tools",
        emojis: [
            "🔧","🛠️","⚙️","🔬","🧪","💻","🖥️","📱","🌐","🚀",
            "🗺️","📡","🔌","🧩","📐","📏","🏗️","🔍","🧲","📊",
        ],
    },
];

export class EmojiPicker extends Component {
    static template = "knowledge.EmojiPicker";
    static props = {
        value: { type: String, optional: true },
        onSelect: Function,
        onClose: Function,
    };

    setup() {
        this.EMOJI_CATEGORIES = EMOJI_CATEGORIES;
        this.state = useState({ activeTab: 0 });
    }

    selectTab(index) {
        this.state.activeTab = index;
    }

    selectEmoji(emoji) {
        this.props.onSelect(emoji);
        this.props.onClose();
    }

    removeIcon() {
        this.props.onSelect("");
        this.props.onClose();
    }
}
```

- [ ] **Step 1.2: Create `emoji_picker.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">

    <!-- ============================================================ -->
    <!-- EmojiPicker — tabbed popover                                  -->
    <!-- ============================================================ -->
    <t t-name="knowledge.EmojiPicker">
        <div class="o_knowledge_emoji_picker" t-on-click.stop="">
            <!-- Category tabs -->
            <div class="o_knowledge_emoji_tabs">
                <t t-foreach="EMOJI_CATEGORIES" t-as="cat" t-key="cat_index">
                    <span class="o_knowledge_emoji_tab"
                          t-att-class="{ active: state.activeTab === cat_index }"
                          t-on-click="() => selectTab(cat_index)"
                          t-out="cat.label"/>
                </t>
            </div>
            <!-- Emoji grid -->
            <div class="o_knowledge_emoji_grid">
                <t t-foreach="EMOJI_CATEGORIES[state.activeTab].emojis" t-as="emoji" t-key="emoji">
                    <span class="o_knowledge_emoji_item"
                          t-att-class="{ selected: props.value === emoji }"
                          t-on-click="() => selectEmoji(emoji)"
                          t-out="emoji"/>
                </t>
            </div>
            <!-- Footer -->
            <div class="o_knowledge_emoji_footer">
                <span class="o_knowledge_emoji_remove" t-on-click="removeIcon">
                    ✕ Remove icon
                </span>
            </div>
        </div>
    </t>

    <!-- ============================================================ -->
    <!-- KnowledgeIconWidget — form view field widget template         -->
    <!-- ============================================================ -->
    <t t-name="knowledge.IconWidget">
        <div class="o_knowledge_icon_field">
            <span class="o_knowledge_icon_trigger"
                  t-att-class="{ 'o_knowledge_icon_readonly': props.readonly }"
                  t-on-click.stop="togglePicker">
                <t t-if="currentValue">
                    <span class="o_knowledge_icon_display" t-out="currentValue"/>
                </t>
                <t t-else="">
                    <span class="o_knowledge_icon_placeholder">+ icon</span>
                </t>
            </span>
            <EmojiPicker t-if="pickerState.open and !props.readonly"
                         value="currentValue"
                         onSelect.bind="onSelectEmoji"
                         onClose.bind="onClosePicker"/>
        </div>
    </t>

</templates>
```

- [ ] **Step 1.3: Commit**

```bash
git add odoo/addons/knowledge/static/src/js/emoji_picker.js \
        odoo/addons/knowledge/static/src/xml/emoji_picker.xml
git commit -m "feat(knowledge): add EmojiPicker OWL component with 4-tab emoji grid"
```

---

## Task 2: Add picker styles

**Files:**
- Modify: `knowledge/static/src/scss/knowledge.scss` (append after line 212)

- [ ] **Step 2.1: Append styles to `knowledge.scss`**

Add at the very end of the file:

```scss
// ---------------------------------------------------------------------------
// Emoji picker popover
// ---------------------------------------------------------------------------

.o_knowledge_emoji_picker {
    position: absolute;
    z-index: 1050;
    background: #fff;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 12px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
    min-width: 280px;

    .o_knowledge_emoji_tabs {
        display: flex;
        gap: 10px;
        margin-bottom: 10px;
        border-bottom: 1px solid #dee2e6;
        padding-bottom: 8px;
        flex-wrap: wrap;

        .o_knowledge_emoji_tab {
            font-size: 0.78rem;
            cursor: pointer;
            color: #6c757d;
            padding-bottom: 4px;

            &.active {
                font-weight: 600;
                color: #7c3aed;
                border-bottom: 2px solid #7c3aed;
            }

            &:hover:not(.active) {
                color: #495057;
            }
        }
    }

    .o_knowledge_emoji_grid {
        display: flex;
        flex-wrap: wrap;
        gap: 2px;

        .o_knowledge_emoji_item {
            font-size: 1.3rem;
            cursor: pointer;
            padding: 4px;
            border-radius: 4px;
            line-height: 1.4;

            &:hover,
            &.selected {
                background: #f0e6ff;
            }
        }
    }

    .o_knowledge_emoji_footer {
        margin-top: 10px;
        padding-top: 8px;
        border-top: 1px solid #dee2e6;

        .o_knowledge_emoji_remove {
            font-size: 0.78rem;
            color: #dc3545;
            cursor: pointer;

            &:hover {
                text-decoration: underline;
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Icon trigger in Knowledge Client Action title area
// ---------------------------------------------------------------------------

.o_knowledge_title {
    .o_knowledge_icon_wrapper {
        position: relative;
        display: inline-flex;
        align-items: center;
        cursor: pointer;

        .o_knowledge_icon {
            border-radius: 6px;
            padding: 2px 4px;
            transition: background-color 0.15s;
        }

        &:hover .o_knowledge_icon {
            background: #f0f0f0;
        }
    }

    .o_knowledge_icon_placeholder {
        font-size: 0.85rem;
        color: #adb5bd;
        border: 1px dashed #ced4da;
        border-radius: 6px;
        padding: 3px 8px;
        cursor: pointer;
        transition: background-color 0.15s, color 0.15s;

        &:hover {
            background: #f8f9fa;
            color: #6c757d;
        }
    }
}

// ---------------------------------------------------------------------------
// KnowledgeIconWidget in backend form view
// ---------------------------------------------------------------------------

.o_knowledge_icon_field {
    position: relative;
    display: inline-flex;
    align-items: center;

    .o_knowledge_icon_trigger {
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border: 1px solid #dee2e6;
        border-radius: 6px;
        background: #f8f9fa;
        transition: background-color 0.15s, border-color 0.15s;

        &:not(.o_knowledge_icon_readonly):hover {
            background: #e9ecef;
            border-color: #adb5bd;
        }

        &.o_knowledge_icon_readonly {
            cursor: default;
            background: transparent;
            border-color: transparent;
        }

        .o_knowledge_icon_display {
            font-size: 1.5rem;
            line-height: 1.2;
        }

        .o_knowledge_icon_placeholder {
            font-size: 0.85rem;
            color: #adb5bd;
        }
    }
}
```

- [ ] **Step 2.2: Commit**

```bash
git add odoo/addons/knowledge/static/src/scss/knowledge.scss
git commit -m "feat(knowledge): add emoji picker and icon widget styles"
```

---

## Task 3: Integrate EmojiPicker into the Knowledge Client Action

**Files:**
- Modify: `knowledge/static/src/js/knowledge_client_action.js`
- Modify: `knowledge/static/src/xml/knowledge_client_action.xml`

### 3a — JS changes

- [ ] **Step 3.1: Add `EmojiPicker` import at the top of `knowledge_client_action.js`**

Find line 12 (after the `HtmlViewer` import):

```javascript
import { HtmlViewer } from "@html_editor/components/html_viewer/html_viewer";
```

Add immediately after it:

```javascript
import { EmojiPicker } from "./emoji_picker";
```

- [ ] **Step 3.2: Add `EmojiPicker` to `static components` (line 128)**

Change:
```javascript
static components = { KnowledgeSidebarItem, KnowledgeCategoryItem, Wysiwyg, HtmlViewer };
```
To:
```javascript
static components = { KnowledgeSidebarItem, KnowledgeCategoryItem, Wysiwyg, HtmlViewer, EmojiPicker };
```

- [ ] **Step 3.3: Add `showIconPicker: false` to the `useState` block (around line 138)**

Change:
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
});
```
To:
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
});
```

- [ ] **Step 3.4: Add click-outside effect to close the picker — place it after the existing `useEffect` block (after line 163)**

Add this block immediately after the closing `);` of the existing `useEffect`:

```javascript
        useEffect(
            () => {
                if (!this.state.showIconPicker) return;
                const handler = () => { this.state.showIconPicker = false; };
                document.addEventListener("click", handler);
                return () => document.removeEventListener("click", handler);
            },
            () => [this.state.showIconPicker]
        );
```

- [ ] **Step 3.5: Add icon picker methods — place them after `onTitleInput` (after line 319)**

Add after the closing `}` of `onTitleInput`:

```javascript
    onIconClick() {
        if (!this.state.activeArticle) return;
        if (!this.state.activeArticle.user_has_write_access || this.state.activeArticle.is_locked) return;
        this.state.showIconPicker = !this.state.showIconPicker;
    }

    onClosePicker() {
        this.state.showIconPicker = false;
    }

    async onPickEmoji(emoji) {
        if (!this.state.activeArticle) return;
        this.state.activeArticle.icon = emoji;
        this.state.showIconPicker = false;
        await this._saveArticle({ icon: emoji });
        this._updateSidebarIcon(this.state.activeArticle.id, emoji);
    }

    _updateSidebarIcon(articleId, emoji) {
        const updateInList = (list) => {
            for (const node of list) {
                if (node.type !== "category" && node.id === articleId) {
                    node.icon = emoji;
                    return true;
                }
                if (node.children?.length && updateInList(node.children)) return true;
            }
            return false;
        };
        updateInList(this.state.sidebar.workspace || []);
        updateInList(this.state.sidebar.shared || []);
        updateInList(this.state.sidebar.private || []);
        updateInList(this.state.sidebar.favorites || []);
    }
```

### 3b — XML template changes

- [ ] **Step 3.6: Replace the static icon display in the article title (lines 362–374 of `knowledge_client_action.xml`)**

Find this block:
```xml
                            <!-- Title -->
                            <div class="o_knowledge_title mb-3">
                                <h1 class="d-flex align-items-center gap-2">
                                    <span t-if="state.activeArticle.icon"
                                          class="o_knowledge_icon"
                                          t-out="state.activeArticle.icon"/>
                                    <span t-att-contenteditable="state.activeArticle.user_has_write_access and !state.activeArticle.is_locked ? 'true' : 'false'"
                                          class="outline-0 flex-grow-1"
                                          t-on-input="onTitleInput"
                                          t-ref="titleSpan"
                                          t-key="wysiwygKey"/>
                                </h1>
                            </div>
```

Replace it with:
```xml
                            <!-- Title -->
                            <div class="o_knowledge_title mb-3">
                                <h1 class="d-flex align-items-center gap-2">
                                    <t t-if="state.activeArticle.user_has_write_access and !state.activeArticle.is_locked">
                                        <span class="o_knowledge_icon_wrapper"
                                              t-on-click.stop="onIconClick">
                                            <span t-if="state.activeArticle.icon"
                                                  class="o_knowledge_icon"
                                                  t-out="state.activeArticle.icon"/>
                                            <span t-else=""
                                                  class="o_knowledge_icon_placeholder">+ icon</span>
                                        </span>
                                        <EmojiPicker t-if="state.showIconPicker"
                                                     value="state.activeArticle.icon"
                                                     onSelect.bind="onPickEmoji"
                                                     onClose.bind="onClosePicker"/>
                                    </t>
                                    <t t-else="">
                                        <span t-if="state.activeArticle.icon"
                                              class="o_knowledge_icon"
                                              t-out="state.activeArticle.icon"/>
                                    </t>
                                    <span t-att-contenteditable="state.activeArticle.user_has_write_access and !state.activeArticle.is_locked ? 'true' : 'false'"
                                          class="outline-0 flex-grow-1"
                                          t-on-input="onTitleInput"
                                          t-ref="titleSpan"
                                          t-key="wysiwygKey"/>
                                </h1>
                            </div>
```

- [ ] **Step 3.7: Commit**

```bash
git add odoo/addons/knowledge/static/src/js/knowledge_client_action.js \
        odoo/addons/knowledge/static/src/xml/knowledge_client_action.xml
git commit -m "feat(knowledge): integrate EmojiPicker into Knowledge client action title area"
```

---

## Task 4: Create the backend form view field widget

**Files:**
- Create: `knowledge/static/src/js/knowledge_icon_widget.js`

- [ ] **Step 4.1: Create `knowledge_icon_widget.js`**

```javascript
/** @odoo-module **/

import { Component, useState, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { EmojiPicker } from "./emoji_picker";

class KnowledgeIconWidget extends Component {
    static template = "knowledge.IconWidget";
    static props = { ...standardFieldProps };
    static components = { EmojiPicker };

    setup() {
        this.pickerState = useState({ open: false });

        useEffect(
            () => {
                if (!this.pickerState.open) return;
                const handler = () => { this.pickerState.open = false; };
                document.addEventListener("click", handler);
                return () => document.removeEventListener("click", handler);
            },
            () => [this.pickerState.open]
        );
    }

    get currentValue() {
        return this.props.record.data[this.props.name] || "";
    }

    togglePicker() {
        if (this.props.readonly) return;
        this.pickerState.open = !this.pickerState.open;
    }

    onSelectEmoji(emoji) {
        this.props.record.update({ [this.props.name]: emoji });
        this.pickerState.open = false;
    }

    onClosePicker() {
        this.pickerState.open = false;
    }
}

registry.category("fields").add("knowledge_icon_picker", {
    component: KnowledgeIconWidget,
    supportedTypes: ["char"],
});
```

- [ ] **Step 4.2: Commit**

```bash
git add odoo/addons/knowledge/static/src/js/knowledge_icon_widget.js
git commit -m "feat(knowledge): add KnowledgeIconWidget field widget for form view"
```

---

## Task 5: Use the widget in the form view

**Files:**
- Modify: `knowledge/views/knowledge_article_views.xml:134`

- [ ] **Step 5.1: Replace the plain icon field with the widget**

Find line 134 in `knowledge_article_views.xml`:
```xml
                            <field name="icon" placeholder="📄" class="d-inline w-auto me-1"/>
```

Replace with:
```xml
                            <field name="icon" widget="knowledge_icon_picker"/>
```

- [ ] **Step 5.2: Commit**

```bash
git add odoo/addons/knowledge/views/knowledge_article_views.xml
git commit -m "feat(knowledge): use knowledge_icon_picker widget in article form view"
```

---

## Task 6: Register new assets in `__manifest__.py`

**Files:**
- Modify: `knowledge/__manifest__.py:44-49`

- [ ] **Step 6.1: Add the three new files to `web.assets_backend`**

Find the assets block:
```python
    "assets": {
        "web.assets_backend": [
            "knowledge/static/src/scss/knowledge.scss",
            "knowledge/static/src/js/knowledge_client_action.js",
            "knowledge/static/src/xml/knowledge_client_action.xml",
        ],
    },
```

Replace with:
```python
    "assets": {
        "web.assets_backend": [
            "knowledge/static/src/scss/knowledge.scss",
            "knowledge/static/src/js/emoji_picker.js",
            "knowledge/static/src/js/knowledge_icon_widget.js",
            "knowledge/static/src/js/knowledge_client_action.js",
            "knowledge/static/src/xml/emoji_picker.xml",
            "knowledge/static/src/xml/knowledge_client_action.xml",
        ],
    },
```

> **Note:** JS files are ordered so `emoji_picker.js` is loaded before the files that import it. XML templates can be in any order as OWL resolves them by name at runtime.

- [ ] **Step 6.2: Commit**

```bash
git add odoo/addons/knowledge/__manifest__.py
git commit -m "feat(knowledge): register emoji_picker and knowledge_icon_widget assets"
```

---

## Task 7: End-to-end verification

- [ ] **Step 7.1: Update the module**

```bash
./odoo-bin -d <your_db> -u knowledge --stop-after-init
```

Expected: no Python errors, module updates cleanly.

- [ ] **Step 7.2: Verify the Knowledge Client Action — icon set**

1. Open the Knowledge module in the browser
2. Create a new article (or open an existing one you have write access to)
3. The title area should show a `+ icon` placeholder to the left of the title text
4. Click `+ icon` → the emoji picker popover opens with 4 tabs (📄 Docs / ✅ Status / 👤 People / 🔧 Tools)
5. Click a tab → the emoji grid updates
6. Click an emoji → the popover closes, the emoji appears in the title and in the sidebar item immediately

- [ ] **Step 7.3: Verify icon removal**

1. With an icon set, click the icon in the title → picker opens
2. Click `✕ Remove icon` → picker closes, icon disappears, `+ icon` placeholder shows again
3. Reload the page → icon is still absent (removal was saved)

- [ ] **Step 7.4: Verify read-only behaviour**

1. Open a locked article, or an article you only have read access to
2. The icon should display normally (no `o_knowledge_icon_wrapper`, no click handler)
3. Clicking the icon should do nothing

- [ ] **Step 7.5: Verify persistence**

1. Set an emoji on an article
2. Reload the page / navigate away and back
3. The emoji should still be set (saved via `/knowledge/article/save`)

- [ ] **Step 7.6: Verify the backend form view**

1. Navigate to an article's form view (via the "Open form" button in the client action, or Settings → Technical → Knowledge articles)
2. The `icon` field should show the `KnowledgeIconWidget` — a styled box with the current emoji (or `+ icon` placeholder)
3. Click it → picker opens
4. Select an emoji → the field value updates
5. Save the form → icon persists

- [ ] **Step 7.7: Verify icon display in list and kanban views (unchanged)**

1. Open Knowledge → List view → icon column still displays emoji correctly
2. Open Knowledge → Kanban view → card icon still displays correctly
