import { FormController } from "@web/views/form/form_controller";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

import { AttachmentHistoryDialog } from "./attachment_history_dialog";

// Kept in step with `TRACKED_MODELS` in models/project_attachment_log.py.
const TRACKED_MODELS = ["project.task", "project.project"];

patch(FormController.prototype, {
    /**
     * Add "Attachment History" next to the "Version History" entry that
     * `ProjectTaskFormController` already puts in the cog menu. Patching the
     * generic controller covers the task and the project form at once.
     */
    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);
        if (!TRACKED_MODELS.includes(this.props.resModel) || !this.model.root.resId) {
            return items;
        }
        return {
            ...items,
            openAttachmentHistory: {
                sequence: 16,
                icon: "fa fa-paperclip",
                description: _t("Attachment History"),
                callback: () =>
                    this.dialogService.add(AttachmentHistoryDialog, {
                        resModel: this.props.resModel,
                        resId: this.model.root.resId,
                    }),
            },
        };
    },
});
