import { _t } from "@web/core/l10n/translation";
import { markup } from "@odoo/owl";

export const DESCRIPTION_FIELD_NAME = "description";

export const descriptionHistoryDialogTitle = _t("Task Description History");

export const descriptionHistoryEmptyMessage = _t(
    "The task description lacks any past content that could be restored at the moment."
);

/**
 * Built on call so that the lazy `_t` is only resolved once translations are loaded.
 */
export function getDescriptionHistoryNoContentHelper() {
    return markup`
        <span class='text-muted fst-italic'>${_t(
            "The task description was empty at the time."
        )}</span>`;
}
