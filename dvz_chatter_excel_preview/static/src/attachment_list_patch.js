/** @odoo-module **/

import { AttachmentList } from "@mail/core/common/attachment_list";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ExcelPreviewDialog } from "./excel_preview_dialog";
import { canPreviewSpreadsheet } from "./preview_helpers";

patch(AttachmentList.prototype, {
    onClickAttachment(attachment) {
        if (!canPreviewSpreadsheet(attachment)) {
            return super.onClickAttachment(...arguments);
        }
        // The native card has nested click handlers. Deduplicate bubbling and
        // repeated clicks while a preview from this attachment list is open.
        if (this._dvzExcelPreviewOpen) return;
        this._dvzExcelPreviewOpen = true;
        try {
            return this.dialog.add(ExcelPreviewDialog, {
                attachmentId: attachment.id,
                filename: attachment.name || _t("Spreadsheet"),
            }, { onClose: () => { this._dvzExcelPreviewOpen = false; } });
        } catch (error) {
            this._dvzExcelPreviewOpen = false;
            throw error;
        }
    },
    getActions(attachment) {
        const actions = super.getActions(...arguments);
        if (canPreviewSpreadsheet(attachment)) {
            actions.unshift({
                label: _t("Preview spreadsheet"),
                icon: "fa fa-table",
                onSelect: () => this.onClickAttachment(attachment),
            });
        }
        return actions;
    },
});
