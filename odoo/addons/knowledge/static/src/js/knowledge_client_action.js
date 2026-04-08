/** @odoo-module **/

import { Component, onWillStart, useState, markup, useRef, useEffect } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { Wysiwyg } from "@html_editor/wysiwyg";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { HtmlViewer } from "@html_editor/components/html_viewer/html_viewer";

// ---------------------------------------------------------------------------
// KnowledgeSidebarItem — renders a single article node (recursive)
// ---------------------------------------------------------------------------

class KnowledgeSidebarItem extends Component {
    static template = "knowledge.SidebarItem";
    static props = {
        article: Object,
        depth: { type: Number, optional: true },
        activeId: { type: Number, optional: true },
        onSelect: Function,
        onToggle: Function,
        onDragStart: { type: Function, optional: true },
    };

    get isActive() {
        return this.props.article.id === this.props.activeId;
    }

    get hasChildren() {
        return this.props.article.has_children;
    }

    get isExpanded() {
        return this.props.article.is_expanded;
    }

    get depth() {
        return this.props.depth || 0;
    }

    get paddingStyle() {
        return `padding-left: ${this.depth * 20 + 8}px`;
    }

    onClickArticle(ev) {
        ev.stopPropagation();
        this.props.onSelect(this.props.article.id);
    }

    onClickToggle(ev) {
        ev.stopPropagation();
        this.props.onToggle(this.props.article.id);
    }

    onDragStartItem(ev) {
        if (this.props.onDragStart) {
            this.props.onDragStart(
                ev,
                this.props.article.id,
                this.props.article.category,
                this.props.article.knowledge_category_id || false,
            );
        }
    }
}
KnowledgeSidebarItem.components = { KnowledgeSidebarItem };

// ---------------------------------------------------------------------------
// KnowledgeCategoryItem — renders a category folder node (recursive)
// ---------------------------------------------------------------------------

class KnowledgeCategoryItem extends Component {
    static template = "knowledge.CategoryItem";
    static props = {
        node: Object,
        depth: { type: Number, optional: true },
        activeId: { type: Number, optional: true },
        onSelect: Function,
        onToggle: Function,
        onToggleCategory: Function,
        onDragStart: Function,
        onDragOver: Function,
        onDrop: Function,
    };

    get isExpanded() {
        return this.props.node.is_expanded;
    }

    get depth() {
        return this.props.depth || 0;
    }

    get paddingStyle() {
        return `padding-left: ${this.depth * 20 + 8}px`;
    }

    onClickToggle(ev) {
        ev.stopPropagation();
        this.props.onToggleCategory(this.props.node.id);
    }

    onDragOverCategory(ev) {
        this.props.onDragOver(ev);
        ev.currentTarget.classList.add("o_knowledge_drop_target");
    }

    onDragLeaveCategory(ev) {
        ev.currentTarget.classList.remove("o_knowledge_drop_target");
    }

    onDropOnCategory(ev) {
        ev.currentTarget.classList.remove("o_knowledge_drop_target");
        this.props.onDrop(ev, "shared", this.props.node.id);
    }
}
KnowledgeCategoryItem.components = { KnowledgeCategoryItem, KnowledgeSidebarItem };

// ---------------------------------------------------------------------------
// KnowledgeClientAction — main component
// ---------------------------------------------------------------------------

class KnowledgeClientAction extends Component {
    static template = "knowledge.ClientAction";
    static components = { KnowledgeSidebarItem, KnowledgeCategoryItem, Wysiwyg, HtmlViewer };
    static props = { ...standardActionServiceProps };
    static path = "knowledge";
    static displayName = _t("Knowledge");

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.editor = null;

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

        this._saveTimeout = null;

        this.titleSpanRef = useRef("titleSpan");
        useEffect(
            () => {
                if (this.titleSpanRef.el) {
                    this.titleSpanRef.el.textContent = this.state.activeArticle?.name || "";
                }
            },
            () => [this.state.activeArticle?.id]
        );

        onWillStart(async () => {
            await this.loadSidebar();
        });
    }

    // --- Wysiwyg integration ---

    get wysiwygKey() {
        return this.state.activeArticle ? this.state.activeArticle.id : 0;
    }

    get isReadonly() {
        if (!this.state.activeArticle) return true;
        return !this.state.activeArticle.user_has_write_access || this.state.activeArticle.is_locked;
    }

    getWysiwygConfig() {
        return {
            content: markup(this.state.activeArticle?.body || ""),
            Plugins: MAIN_PLUGINS,
            onChange: () => this.onWysiwygChange(),
            baseContainers: ["DIV", "P"],
            dropImageAsAttachment: true,
            getRecordInfo: () => ({
                resModel: "knowledge.article",
                resId: this.state.activeArticle?.id,
            }),
        };
    }

    getReadonlyConfig() {
        return {
            value: markup(this.state.activeArticle?.body || ""),
        };
    }

    onLoadWysiwyg(editor) {
        this.editor = editor;
    }

    onWysiwygChange() {
        if (!this.state.activeArticle || this.isReadonly) return;
        this._debouncedSave({ body: this.editor.getContent() });
    }

    // --- Sidebar ---

    async loadSidebar(activeArticleId = false) {
        const data = await rpc("/knowledge/sidebar", {
            active_article_id: activeArticleId || (this.state.activeArticle?.id || false),
        });
        this.state.sidebar = data;
        this.state.loading = false;
    }

    // --- Article selection ---

    async onSelectArticle(articleId) {
        if (this._saveTimeout) {
            clearTimeout(this._saveTimeout);
            this._saveTimeout = null;
            if (this.editor && this.state.activeArticle) {
                await this._saveArticle({ body: this.editor.getContent() });
            }
        }
        this.editor = null;
        const data = await rpc("/knowledge/article/data", {
            article_id: articleId,
        });
        if (data) {
            this.state.activeArticle = data;
        }
    }

    // --- Expand/collapse article children ---

    async onToggleExpand(articleId) {
        const toggleInList = async (list) => {
            for (const node of list) {
                if (node.type === "category") {
                    if (node.children?.length) {
                        const found = await toggleInList(node.children);
                        if (found) return true;
                    }
                    continue;
                }
                if (node.id === articleId) {
                    if (node.is_expanded) {
                        node.is_expanded = false;
                        node.children = [];
                    } else {
                        const children = await rpc("/knowledge/article/children", {
                            article_id: articleId,
                        });
                        node.children = children;
                        node.is_expanded = true;
                    }
                    return true;
                }
                if (node.children?.length) {
                    const found = await toggleInList(node.children);
                    if (found) return true;
                }
            }
            return false;
        };

        await toggleInList(this.state.sidebar.workspace);
        await toggleInList(this.state.sidebar.shared);
        await toggleInList(this.state.sidebar.private);
    }

    // --- Expand/collapse category folders ---

    onToggleCategory(categoryId) {
        const toggleInList = (list) => {
            for (const node of list) {
                if (node.type === "category" && node.id === categoryId) {
                    node.is_expanded = !node.is_expanded;
                    return true;
                }
                if (node.type === "category" && node.children?.length) {
                    if (toggleInList(node.children)) return true;
                }
            }
            return false;
        };
        toggleInList(this.state.sidebar.shared);
    }

    // --- Article actions ---

    async onToggleFavorite() {
        if (!this.state.activeArticle) return;
        const result = await rpc("/knowledge/article/toggle_favorite", {
            article_id: this.state.activeArticle.id,
        });
        this.state.activeArticle.is_favorite = result.is_favorite;
        await this.loadSidebar(this.state.activeArticle.id);
    }

    async onToggleLock() {
        if (!this.state.activeArticle) return;
        const result = await rpc("/knowledge/article/toggle_lock", {
            article_id: this.state.activeArticle.id,
        });
        this.state.activeArticle.is_locked = result.is_locked;
        this.state.activeArticle.locked_by = result.locked_by;
    }

    onTitleInput(ev) {
        if (!this.state.activeArticle) return;
        this.state.activeArticle.name = ev.target.textContent;
        this._debouncedSave({ name: ev.target.textContent });
    }

    // --- Save ---

    _debouncedSave(vals) {
        if (this._saveTimeout) clearTimeout(this._saveTimeout);
        this._saveTimeout = setTimeout(() => this._saveArticle(vals), 1000);
    }

    async _saveArticle(vals) {
        if (!this.state.activeArticle) return;
        this.state.saving = true;
        await rpc("/knowledge/article/save", {
            article_id: this.state.activeArticle.id,
            vals,
        });
        this.state.saving = false;
    }

    // --- Create ---

    async onCreateArticle(category) {
        const ids = await this.orm.create("knowledge.article", [{ name: _t("Untitled"), category }]);
        if (ids?.length) {
            await this.loadSidebar(ids[0]);
            await this.onSelectArticle(ids[0]);
        }
    }

    async onCreateChildArticle() {
        if (!this.state.activeArticle) return;
        const ids = await this.orm.create("knowledge.article", [{
            name: _t("Untitled"),
            parent_id: this.state.activeArticle.id,
        }]);
        if (ids?.length) {
            await this.loadSidebar(ids[0]);
            await this.onSelectArticle(ids[0]);
        }
    }

    // --- Navigation ---

    onOpenForm() {
        if (!this.state.activeArticle) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "knowledge.article",
            res_id: this.state.activeArticle.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    onShareArticle() {
        if (!this.state.activeArticle) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "knowledge.article.share",
            views: [[false, "form"]],
            target: "new",
            context: { active_id: this.state.activeArticle.id },
        });
    }

    toggleSidebar() {
        this.state.sidebarCollapsed = !this.state.sidebarCollapsed;
    }

    // --- Drag-and-drop ---

    onDragStart(ev, articleId, fromSection, fromCategoryId) {
        ev.dataTransfer.setData(
            "text/plain",
            JSON.stringify({ articleId, fromSection, fromCategoryId }),
        );
        ev.dataTransfer.effectAllowed = "move";
    }

    onDragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
    }

    onDragEnterSection(ev) {
        ev.currentTarget.classList.add("o_knowledge_drop_target");
    }

    onDragLeaveSection(ev) {
        ev.currentTarget.classList.remove("o_knowledge_drop_target");
    }

    async onDrop(ev, toSection, toCategoryId = false) {
        ev.preventDefault();
        ev.currentTarget.classList.remove("o_knowledge_drop_target");
        let payload;
        try {
            payload = JSON.parse(ev.dataTransfer.getData("text/plain"));
        } catch {
            return;
        }
        if (!payload?.articleId) return;
        await rpc("/knowledge/article/move_to_section", {
            article_id: payload.articleId,
            category: toSection,
            knowledge_category_id: toCategoryId || false,
        });
        await this.loadSidebar(this.state.activeArticle?.id);
    }

    // --- Remove share (Shared with me section) ---

    async onRemoveShare(memberId) {
        if (!memberId) return;
        await rpc("/knowledge/article/remove_member", { member_id: memberId });
        await this.loadSidebar(this.state.activeArticle?.id);
    }

    // --- PDF ---

    getPdfViewerUrl(pdfId) {
        return `/web/static/lib/pdfjs/web/viewer.html?file=${encodeURIComponent('/web/content/' + pdfId)}`;
    }

    async onUploadPdf() {
        if (!this.state.activeArticle) return;
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".pdf";
        input.onchange = async (ev) => {
            const file = ev.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = async (e) => {
                const base64Data = e.target.result.split(",")[1];
                await rpc("/knowledge/article/upload_pdf", {
                    article_id: this.state.activeArticle.id,
                    file_name: file.name,
                    file_data: base64Data,
                });
                await this.onSelectArticle(this.state.activeArticle.id);
            };
            reader.readAsDataURL(file);
        };
        input.click();
    }

    async onDeletePdf(attachmentId) {
        await rpc("/knowledge/article/delete_pdf", { attachment_id: attachmentId });
        await this.onSelectArticle(this.state.activeArticle.id);
    }

    async onConvertPdfToArticle(attachmentId) {
        const result = await rpc("/knowledge/article/convert_pdf", {
            article_id: this.state.activeArticle.id,
            attachment_id: attachmentId,
        });
        if (result && result.error) {
            console.warn("PDF conversion failed:", result.error);
            return;
        }
        await this.onSelectArticle(this.state.activeArticle.id);
    }
}

registry.category("actions").add("knowledge.articles", KnowledgeClientAction);
