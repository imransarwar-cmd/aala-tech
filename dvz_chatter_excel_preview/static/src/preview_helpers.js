/** @odoo-module **/

export function canPreviewSpreadsheet(attachment) {
    if (!attachment || attachment.type === "url" || attachment.uploading) {
        return false;
    }
    if (!Number.isInteger(attachment.id) || attachment.id <= 0) {
        return false;
    }
    return /\.(xlsx|xlsm|csv)$/i.test(attachment.name || "");
}

// Allow only known style tokens; never inject arbitrary styles from a workbook.
export function cellStyle(style = {}, wrap = false) {
    const values = [];
    if (style.bold) values.push("font-weight:700");
    if (style.italic) values.push("font-style:italic");
    if (style.underline) values.push("text-decoration:underline");
    if (/^#[0-9A-Fa-f]{6}$/.test(style.color || "")) values.push(`color:${style.color}`);
    if (/^#[0-9A-Fa-f]{6}$/.test(style.background || "")) values.push(`background-color:${style.background}`);
    if (["left", "right", "center"].includes(style.align)) values.push(`text-align:${style.align}`);
    if (wrap || style.wrap) values.push("white-space:pre-wrap;overflow-wrap:anywhere");
    return values.join(";");
}

export function matchesText(text, query) {
    const needle = String(query || "").trim().toLocaleLowerCase();
    return !!needle && String(text || "").toLocaleLowerCase().includes(needle);
}
