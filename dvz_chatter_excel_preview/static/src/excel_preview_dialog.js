/** @odoo-module **/

import { Component, onMounted, onWillDestroy, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { downloadFile } from "@web/core/network/download";
import { useService } from "@web/core/utils/hooks";
import { cellStyle, matchesText } from "./preview_helpers";

export class ExcelPreviewDialog extends Component {
    static template = "dvz_chatter_excel_preview.ExcelPreviewDialog";
    static components = { Dialog };
    static props = {
        attachmentId: Number,
        filename: String,
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.grid = useRef("grid");
        this.state = useState({
            loading: true, error: "", data: null, query: "", selected: null,
            wrap: false, zoom: "100", fullscreen: false,
        });
        this._request = 0;
        this._destroyed = false;
        onMounted(() => this.load(0, 0));
        onWillDestroy(() => { this._destroyed = true; this._request++; });
    }

    get title() {
        return _t("Excel Preview — %s", this.props.filename);
    }

    get pageLabel() {
        const data = this.state.data;
        if (!data) return "";
        if (!data.preview_rows) return _t("Empty worksheet");
        return _t("Rows %s–%s of %s previewable rows", data.offset + 1,
            Math.min(data.offset + data.page_size, data.preview_rows), data.preview_rows);
    }

    get matchingCells() {
        if (!this.state.data || !this.state.query.trim()) return 0;
        return this.state.data.rows.reduce((count, row) => count + row.cells.filter(
            (cell) => !cell.hidden && matchesText(cell.text, this.state.query)
        ).length, 0);
    }

    get tableStyle() {
        return `font-size:${["80", "100", "120", "140"].includes(this.state.zoom) ? Number(this.state.zoom) / 100 * 13 : 13}px`;
    }

    styleFor(cell) {
        return cellStyle(cell.style, this.state.wrap);
    }

    isMatch(cell) {
        return matchesText(cell.text, this.state.query);
    }

    async load(sheetIndex, offset) {
        const token = ++this._request;
        this.state.loading = true;
        this.state.error = "";
        this.state.selected = null;
        this.state.query = "";
        // Remove stale page data immediately if a later permission check fails.
        this.state.data = null;
        this._lastPage = { sheetIndex, offset };
        try {
            const data = await this.orm.call("ir.attachment", "dvz_excel_preview", [[this.props.attachmentId]], {
                sheet_index: sheetIndex, offset,
            });
            if (this._destroyed || token !== this._request) return;
            this.state.data = data;
            if (this.grid.el) this.grid.el.scrollTo({ top: 0, left: 0 });
        } catch (error) {
            if (this._destroyed || token !== this._request) return;
            this.state.error = error?.data?.message || _t("Preview is unavailable. Check access to this attachment or download the original file.");
        } finally {
            if (!this._destroyed && token === this._request) this.state.loading = false;
        }
    }

    changeSheet(index) {
        if (!this.state.loading) return this.load(index, 0);
    }
    previousPage() {
        const data = this.state.data;
        if (!this.state.loading && data?.has_previous) return this.load(data.sheet_index, data.offset - data.page_size);
    }
    nextPage() {
        const data = this.state.data;
        if (!this.state.loading && data?.has_next) return this.load(data.sheet_index, data.offset + data.page_size);
    }
    retry() {
        const page = this._lastPage || { sheetIndex: 0, offset: 0 };
        return this.load(page.sheetIndex, page.offset);
    }
    download() {
        // Same-origin, native authenticated endpoint. Never accept external URLs
        // or access tokens as RPC input. This does not change the native tile's
        // Download button or its existing Odoo behavior.
        downloadFile(`/web/content/${this.props.attachmentId}?download=true`);
    }
    expand() {
        this.state.fullscreen = !this.state.fullscreen;
    }
    selectCell(cell) {
        this.state.selected = cell;
    }
}
