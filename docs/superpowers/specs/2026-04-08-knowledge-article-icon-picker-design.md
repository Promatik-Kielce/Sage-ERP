# Knowledge Article Icon Picker — Design Spec

**Date:** 2026-04-08
**Branch:** knoweledge-module

---

## Problem

The `knowledge.article` model already has an `icon` field (a `Char` storing a Unicode emoji character). Currently it is exposed as a plain text input in the backend form view, and not editable at all in the main Knowledge OWL client action view. Users have no easy way to discover or select icons — they must know to type an emoji manually. This creates an inconsistent, low-discoverability experience.

## Goal

Replace the plain-text `icon` input with a click-to-open emoji picker popover across all views where an article can be edited. No changes to the data model — `icon` stays a `Char` field storing a single emoji character.

---

## Decisions Made

| Question | Decision |
|---|---|
| Icon type | Emoji only (Unicode chars, matches existing field) |
| Picker trigger | Click the icon (or "+ icon" placeholder) to open popover |
| Emoji set | Medium (~80 emojis), organised into 4 category tabs |
| Clear option | Yes — "Remove icon" button inside the picker |
| Architecture | Shared `EmojiPicker` OWL component, reused in client action + form view widget |

---

## Emoji Categories (~80 total)

| Tab | Label | Emojis (~20 each) |
|---|---|---|
| 1 | 📄 Docs | 📄 📁 📝 🗂️ 📎 📊 🔑 🗒️ 📋 📑 🖊️ 📰 📚 📒 📓 📔 📃 📜 🗃️ 🗄️ |
| 2 | ✅ Status | ✅ ❗ ❓ 🔒 🔓 ⭐ 🏷️ 📌 🚩 ⚠️ 🔔 💡 🎯 🔴 🟡 🟢 ⏳ ✔️ ❌ 🔁 |
| 3 | 👤 People | 👤 👥 🧑‍💼 👨‍💻 👩‍💻 🧑‍🏫 👨‍🔬 🤝 👋 🙋 🧠 💬 📣 📢 🗣️ 👁️ 🫂 🤖 👑 🏆 |
| 4 | 🔧 Tools | 🔧 🛠️ ⚙️ 🔬 🧪 💻 🖥️ 📱 🌐 🚀 🗺️ 📡 🔌 💡 🧩 📐 📏 🏗️ 🔍 🧲 |

---

## Architecture

### New files

| File | Purpose |
|---|---|
| `knowledge/static/src/js/emoji_picker.js` | OWL `EmojiPicker` component — all picker logic |
| `knowledge/static/src/xml/emoji_picker.xml` | OWL template for the picker popover |
| `knowledge/static/src/js/knowledge_icon_widget.js` | Custom `CharField` field widget for the backend form view — wraps `EmojiPicker` |

### Modified files

| File | Change |
|---|---|
| `knowledge/static/src/js/knowledge_client_action.js` | Import `EmojiPicker`; add `showIconPicker` state bool; add `onIconClick()` and `onPickEmoji(emoji)` handlers; call `/knowledge/article/save` with new icon |
| `knowledge/static/src/xml/knowledge_client_action.xml` | Replace static `<span class="o_knowledge_icon">` with clickable element; conditionally render `<EmojiPicker>` popover; add "+ icon" placeholder when no icon set |
| `knowledge/views/knowledge_article_views.xml` | Replace `<field name="icon" placeholder="📄">` with `<field name="icon" widget="knowledge_icon_picker"/>` in the form view |
| `knowledge/static/src/scss/knowledge.scss` | Add styles for picker popover, tabs, emoji grid, hover states, "Remove icon" button |
| `knowledge/__manifest__.py` | Add 3 new assets to `web.assets_backend`: `emoji_picker.js`, `emoji_picker.xml`, `knowledge_icon_widget.js` |

### No backend changes required

The controller already supports everything needed:
- `/knowledge/article/data` (line 32) returns `icon` — `state.activeArticle.icon` is already populated
- `/knowledge/article/save` (line 89-90) already has `"icon"` in `allowed_fields`
- Sidebar RPC methods already include `icon` in all article node dicts

---

## Component Design: `EmojiPicker`

```
Props:
  value: String          — current emoji (or "")
  onSelect: Function     — called with new emoji string (or "" to clear)
  onClose: Function      — called when picker should close (click outside / Escape)

State:
  activeTab: Number      — index of currently selected category tab (default 0)

Behaviour:
  - Renders a floating popover with 4 category tabs
  - Clicking an emoji calls onSelect(emoji) then onClose()
  - "Remove icon" button calls onSelect("") then onClose()
  - Clicking outside the popover calls onClose()
  - Escape key calls onClose()
```

---

## Integration: Knowledge Client Action

- The icon span in the article title becomes clickable when `user_has_write_access && !is_locked`
- When no icon is set, render `<span class="o_knowledge_icon_placeholder">+ icon</span>` instead (also clickable)
- `onIconClick()` toggles `state.showIconPicker`
- `onPickEmoji(emoji)` sets `state.activeArticle.icon = emoji`, closes picker, immediately calls `_saveArticle({ icon: emoji })` via the existing `/knowledge/article/save` RPC
- The `/knowledge/article/save` controller already handles partial field updates — no backend change needed
- The sidebar icon updates automatically because `state.activeArticle` is reactive (OWL)

> **Note:** The sidebar tree item icons will not update until the next sidebar reload (e.g. navigating away and back). This is acceptable — the title area updates immediately.

---

## Integration: Backend Form View Widget (`knowledge_icon_widget`)

- Extends `CharField` from `@web/views/fields/char/char_field`
- In edit mode: renders the current emoji in a clickable `<span>`, toggling `EmojiPicker` visibility
- In readonly mode: renders the emoji as plain text (same as before)
- On emoji select: calls `this.props.update(emoji)` (standard field widget update API)
- The widget is registered under the name `knowledge_icon_picker`

---

## Save Flow

| View | How icon is saved |
|---|---|
| Knowledge Client Action | `onPickEmoji` → `_saveArticle({ icon: emoji })` → `/knowledge/article/save` RPC |
| Backend Form View | `EmojiPicker.onSelect` → `CharField.props.update(emoji)` → standard Odoo form save |

---

## Scope: Views Where Icon Is Editable

| View | Before | After |
|---|---|---|
| Knowledge Client Action (OWL) | Not editable | Click icon/placeholder → picker |
| Backend Form View | Plain text input | `knowledge_icon_picker` widget |
| List View | Read-only display column | Unchanged (display only) |
| Kanban View | Read-only card display | Unchanged (display only) |
| Sidebar | Read-only display | Unchanged (display only) |

---

## Verification

1. Open the Knowledge module → create a new article → click "+ icon" in the title → picker opens → select an emoji → picker closes, icon appears in title and sidebar immediately.
2. Reload the page → icon persists (was saved via RPC).
3. Open the same article → click the icon → "Remove icon" → icon disappears, placeholder shown.
4. Open the article in the backend form view (Settings → Technical or direct URL) → click the icon widget → picker opens → select → save the form → icon updated.
5. Verify icon appears correctly in list view, kanban view, and sidebar after changes.
6. Verify icon is not editable when article is locked or user lacks write access.
