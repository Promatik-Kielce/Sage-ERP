import { Component, onMounted, onWillDestroy, onWillStart, useState } from "@odoo/owl";

import { Dialog } from "@web/core/dialog/dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import { formatDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { browser } from "@web/core/browser/browser";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { download } from "@web/core/network/download";

const { DateTime } = luxon;

// Sentinel for "the live state", mirroring `CURRENT_REVISION` server side and
// the same convention `HistoryDialog` uses for html fields.
export const CURRENT_REVISION = -1;

/**
 * Shows the attachments of a task or a project as they stood at a point in time.
 *
 * Deliberately a sibling of `@html_editor/components/history_dialog/history_dialog`
 * rather than a reuse of it: that one is welded to html field revisions. The
 * markup contract is shared on purpose (`html-history-dialog`, `revision-list`,
 * `selected` / `targeted`) so the timeline rail is styled by the very same rules.
 */
export class AttachmentHistoryDialog extends Component {
    static template = "project_attachment_history.AttachmentHistoryDialog";
    static components = { Dialog };
    static props = {
        resModel: String,
        resId: Number,
        close: Function,
        title: { type: String, optional: true },
    };
    static defaultProps = {
        title: _t("Attachment History"),
    };

    DEFAULT_AVATAR = "/mail/static/src/img/smiley/avatar.jpg";

    setup() {
        this.size = "fullscreen";
        this.orm = useService("orm");
        this.store = useService("mail.store");
        this.dialogService = useService("dialog");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.fileViewer = useFileViewer();
        this.snapshotCache = new Map();

        this.state = useState({
            revisionsData: [],
            revisionId: null,
            files: [],
            summary: "",
            loading: true,
            cssMaxHeight: 400,
        });

        onWillStart(async () => {
            const history = await this.orm.call(
                "project.attachment.log",
                "get_attachment_history",
                [this.props.resModel, this.props.resId]
            );
            this.state.revisionsData = this.buildRevisions(history);
            this.resizeObserver = new ResizeObserver(this.resize.bind(this));
            this.resizeObserver.observe(document.body);
        });
        onMounted(() => this.updateCurrentRevision(CURRENT_REVISION));
        onWillDestroy(() => this.resizeObserver?.disconnect());
    }

    /**
     * The rail: "Current" on top, then one entry per audited event, and the
     * creation of the record itself at the bottom.
     */
    buildRevisions(history) {
        const revisions = [
            {
                revision_id: CURRENT_REVISION,
                create_date: null,
                create_uid: null,
                create_user_name: "",
                summary: _t("Current files"),
                isCurrent: true,
            },
            ...history.revisions,
        ];
        if (history.record?.create_date) {
            revisions.push({
                revision_id: 0,
                create_date: history.record.create_date,
                create_uid: history.record.create_uid,
                create_user_name: history.record.create_user_name,
                summary: _t("Record created"),
                isCreation: true,
            });
        }
        return revisions;
    }

    resize() {
        const container = document.querySelector(".html-history-dialog-container");
        if (container) {
            this.state.cssMaxHeight = Math.max(container.offsetHeight - 160, 200);
        }
    }

    async updateCurrentRevision(revisionId) {
        if (this.state.revisionId === revisionId) {
            return;
        }
        this.state.loading = true;
        this.state.revisionId = revisionId;
        const snapshot = await this.getSnapshot(revisionId);
        // A slower earlier request must not overwrite a newer selection.
        if (this.state.revisionId !== revisionId) {
            return;
        }
        this.state.files = snapshot.files;
        this.state.summary = snapshot.summary;
        this.state.loading = false;
        this.resize();
    }

    /**
     * One snapshot per revision, cached. A local `Map` rather than `memoize`
     * because a restore changes the past-is-fixed assumption and the cache has
     * to be dropped.
     */
    async getSnapshot(revisionId) {
        if (!this.snapshotCache.has(revisionId)) {
            this.snapshotCache.set(revisionId, this.fetchSnapshot(revisionId));
        }
        return this.snapshotCache.get(revisionId);
    }

    async fetchSnapshot(revisionId) {
        const result = await this.orm.call(
            "project.attachment.log",
            "get_attachment_snapshot",
            [this.props.resModel, this.props.resId, revisionId]
        );
        // Feed the mail store so every file gets `downloadUrl`, `defaultSource`
        // and `isViewable` from `FileModelMixin` for free.
        this.store.insert(result.store_data);
        const files = result.files.map((entry) => ({
            ...entry,
            attachment: this.store["ir.attachment"].insert({ id: entry.attachment_id }),
        }));
        return { files, summary: result.summary };
    }

    get viewableAttachments() {
        return this.state.files.map((file) => file.attachment).filter((att) => att.isViewable);
    }

    onClickFile(file) {
        if (file.attachment.isViewable) {
            this.fileViewer.open(file.attachment, this.viewableAttachments);
        } else {
            this.onClickDownload(file);
        }
    }

    onClickDownload(file) {
        download({ data: {}, url: file.attachment.downloadUrl });
    }

    async onClickRestoreFile(file) {
        await this.orm.call("project.attachment.log", "action_restore", [[file.restore_log_id]]);
        this.notification.add(_t("File restored."), { type: "success" });
        await this.reload();
    }

    onClickRestoreSnapshot() {
        this.dialogService.add(ConfirmationDialog, {
            title: _t("Restore this version?"),
            body: _t(
                "Files that were present then will be put back, and files added since will be removed. Everything stays recoverable and is recorded in the chatter."
            ),
            confirmLabel: _t("Restore"),
            confirm: async () => {
                await this.orm.call("project.attachment.log", "action_restore_snapshot", [
                    this.props.resModel,
                    this.props.resId,
                    this.state.revisionId,
                ]);
                this.props.close();
                await this.actionService.doAction({
                    type: "ir.actions.client",
                    tag: "soft_reload",
                });
            },
        });
    }

    /** Re-read everything after a restore, since the timeline itself grew. */
    async reload() {
        const revisionId = this.state.revisionId;
        this.snapshotCache.clear();
        const history = await this.orm.call(
            "project.attachment.log",
            "get_attachment_history",
            [this.props.resModel, this.props.resId]
        );
        this.state.revisionsData = this.buildRevisions(history);
        this.state.revisionId = null;
        await this.updateCurrentRevision(revisionId);
    }

    // ------------------------------------------------------------
    // Rail rendering, kept identical to the description history dialog
    // ------------------------------------------------------------

    getRevisionDate(revision) {
        if (!revision || !revision.create_date) {
            return _t("Now");
        }
        const userTZ = user.tz || "local";
        return formatDateTime(
            DateTime.fromISO(revision.create_date, { zone: "utc" }).setZone(userTZ),
            { showSeconds: false }
        );
    }

    getRevisionClasses(revision) {
        let classes = "btn";
        if (
            this.state.revisionId !== CURRENT_REVISION &&
            (this.state.revisionId < revision.revision_id ||
                revision.revision_id === CURRENT_REVISION)
        ) {
            classes += " targeted";
        } else if (this.state.revisionId === revision.revision_id) {
            classes += " selected";
        }
        return classes;
    }

    getRevisionAuthorAvatar(revision) {
        if (!revision || !revision.create_uid) {
            return this.DEFAULT_AVATAR;
        }
        return `${browser.location.origin}/web/image?model=res.users&field=avatar_128&id=${revision.create_uid}`;
    }

    get currentRevision() {
        return this.state.revisionsData.find((rev) => rev.revision_id === this.state.revisionId);
    }

    /** One translatable sentence rather than fragments around a `t-esc`. */
    get revisionCaption() {
        const revision = this.currentRevision;
        if (!revision || revision.isCurrent) {
            return _t("Showing the files currently on this record");
        }
        return _t("Showing the files as they were on %(date)s, after %(user)s %(summary)s", {
            date: this.getRevisionDate(revision),
            user: revision.create_user_name,
            summary: this.state.summary,
        });
    }

    get canRestoreSnapshot() {
        return !this.state.loading && this.state.revisionId !== CURRENT_REVISION;
    }

    formatSize(file) {
        const size = file.attachment.file_size;
        if (!size) {
            return "";
        }
        return size < 1024 ? `${size} B` : `${Math.round(size / 1024)} KB`;
    }

    changedLabel(file) {
        return {
            added: _t("added here"),
            deleted: _t("deleted here"),
            restored: _t("restored here"),
            renamed: _t("renamed here"),
            replaced: _t("content replaced here"),
            moved_in: _t("moved here"),
            moved_out: _t("moved away here"),
        }[file.changed_here];
    }
}
