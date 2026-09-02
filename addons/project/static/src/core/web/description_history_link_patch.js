import { Store } from "@mail/core/common/store_service";
// Ensure this patch is applied after the generic `data-oe-model`/`data-oe-id` link
// handler, so that our link is intercepted before it opens the task form.
import "@mail/core/web/store_service_patch";

import { HistoryDialog } from "@html_editor/components/history_dialog/history_dialog";
import { getHtmlFieldMetadata, setHtmlFieldMetadata } from "@html_editor/fields/html_field";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

import {
    DESCRIPTION_FIELD_NAME,
    descriptionHistoryDialogTitle,
    descriptionHistoryEmptyMessage,
    getDescriptionHistoryNoContentHelper,
} from "@project/views/project_task_form/description_history";

patch(Store.prototype, {
    handleClickOnLink(ev, thread) {
        const link = ev.target.closest("a");
        if (link?.classList.contains("o_project_description_history")) {
            ev.preventDefault();
            this.openTaskDescriptionHistory(Number(link.dataset.oeId));
            return true;
        }
        return super.handleClickOnLink(...arguments);
    },

    /**
     * Open the description history of a task from a chatter note.
     *
     * @param {number} taskId
     */
    async openTaskDescriptionHistory(taskId) {
        const orm = this.env.services.orm;
        const [task] = await orm.read("project.task", [taskId], [
            "html_field_history_metadata",
        ]);
        const historyMetadata = task?.html_field_history_metadata?.[DESCRIPTION_FIELD_NAME];
        if (!historyMetadata) {
            this.env.services.notification.add(descriptionHistoryEmptyMessage);
            return;
        }
        this.env.services.dialog.add(HistoryDialog, {
            title: descriptionHistoryDialogTitle,
            noContentHelper: getDescriptionHistoryNoContentHelper(),
            recordId: taskId,
            recordModel: "project.task",
            versionedFieldName: DESCRIPTION_FIELD_NAME,
            historyMetadata,
            restoreRequested: (html, close) => {
                // Unlike the form view, the chatter has no record to write back to,
                // so the restored content is saved directly and the view reloaded.
                this.env.services.dialog.add(ConfirmationDialog, {
                    title: _t("Are you sure you want to restore this version ?"),
                    body: _t(
                        "Restoring will replace the current content with the selected version. Any unsaved changes will be lost."
                    ),
                    confirmLabel: _t("Restore"),
                    confirm: async () => {
                        // Keep the collaboration metadata of the live value, as the
                        // form view does, so concurrent editors stay in sync.
                        const [current] = await orm.read("project.task", [taskId], [
                            DESCRIPTION_FIELD_NAME,
                        ]);
                        const metadata = getHtmlFieldMetadata(
                            current?.[DESCRIPTION_FIELD_NAME] || ""
                        );
                        await orm.write("project.task", [taskId], {
                            [DESCRIPTION_FIELD_NAME]: setHtmlFieldMetadata(html, metadata),
                        });
                        close();
                        await this.env.services.action.doAction({
                            type: "ir.actions.client",
                            tag: "soft_reload",
                        });
                    },
                });
            },
        });
    },
});
