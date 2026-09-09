import { Store } from "@mail/core/common/store_service";
// Ensure this patch is applied after the generic `data-oe-model`/`data-oe-id` link
// handler, so that our links are intercepted before they open a form view.
import "@mail/core/web/store_service_patch";

import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

import { AttachmentHistoryDialog } from "./attachment_history_dialog";

patch(Store.prototype, {
    handleClickOnLink(ev, thread) {
        const link = ev.target.closest("a");
        if (link?.classList.contains("o_project_attachment_restore")) {
            ev.preventDefault();
            this.restoreProjectAttachment(Number(link.dataset.oeId));
            return true;
        }
        if (link?.classList.contains("o_project_attachment_history")) {
            ev.preventDefault();
            this.openProjectAttachmentHistory(
                link.dataset.oeModel,
                Number(link.dataset.oeId)
            );
            return true;
        }
        return super.handleClickOnLink(...arguments);
    },

    /**
     * Open the attachment timeline of a task or project from a chatter note.
     *
     * @param {string} resModel
     * @param {number} resId
     */
    openProjectAttachmentHistory(resModel, resId) {
        this.env.services.dialog.add(AttachmentHistoryDialog, { resModel, resId });
    },

    /**
     * Restore a soft deleted project/task attachment from its chatter note.
     *
     * @param {number} logId id of the `project.attachment.log` record holding the file
     */
    restoreProjectAttachment(logId) {
        this.env.services.dialog.add(ConfirmationDialog, {
            title: _t("Restore this file?"),
            body: _t("The file will be put back on the record it was deleted from."),
            confirmLabel: _t("Restore"),
            confirm: async () => {
                // Unlike the form view, the chatter has no record to write back
                // to, so the restore is done server side and the view reloaded.
                const action = await this.env.services.orm.call(
                    "project.attachment.log",
                    "action_restore",
                    [[logId]]
                );
                if (action) {
                    await this.env.services.action.doAction(action);
                }
            },
        });
    },
});
