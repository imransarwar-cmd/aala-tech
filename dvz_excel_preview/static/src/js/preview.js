/** @odoo-module **/

import { rpc } from '@web/core/network/rpc';

// Global backend listener: covers chatter and standard attachment links/cards.
// Capturing the event avoids a hard dependency on mail component internals.
const EXTENSION = /\.(xlsx|xls)(?:\s|$|[?#])/i;

function attachmentId(element) {
    const candidates = [element, element.closest('[data-id]'), element.closest('[data-attachment-id]')];
    for (const el of candidates) {
        if (!el) continue;
        const value = el.dataset?.attachmentId || el.dataset?.id;
        if (value && /^\d+$/.test(value)) return Number(value);
    }
    const href = element.closest('a')?.getAttribute('href') || '';
    const match = href.match(/\/web\/content\/(\d+)/) || href.match(/[?&]id=(\d+)/);
    return match ? Number(match[1]) : null;
}

function isExcel(element) {
    const card = element.closest('.o_attachment, .o-mail-Attachment, .o-mail-AttachmentCard, .o_AttachmentCard, [data-attachment-id]');
    const link = element.closest('a');
    const text = [card?.textContent || '', card?.getAttribute('title') || '', link?.getAttribute('download') || '', link?.getAttribute('href') || '', element.getAttribute('title') || ''].join(' ');
    return EXTENSION.test(text);
}

function showPreview(data, id) {
    const overlay = document.createElement('div');
    overlay.className = 'dvz_excel_overlay';
    const modal = document.createElement('div');
    modal.className = 'dvz_excel_modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    const header = document.createElement('header');
    const title = document.createElement('strong');
    title.textContent = data.name || 'Excel Preview';
    const download = document.createElement('a');
    download.textContent = 'Download';
    download.href = `/web/content/${id}?download=true`;
    download.className = 'btn btn-primary';
    const close = document.createElement('button');
    close.textContent = '×';
    close.className = 'btn btn-secondary';
    close.setAttribute('aria-label', 'Close preview');
    const closeModal = () => { overlay.remove(); document.removeEventListener('keydown', escape); };
    const escape = (event) => { if (event.key === 'Escape') closeModal(); };
    close.addEventListener('click', closeModal);
    overlay.addEventListener('click', (event) => { if (event.target === overlay) closeModal(); });
    document.addEventListener('keydown', escape);
    header.append(title, download, close);
    const tabs = document.createElement('nav');
    const content = document.createElement('section');
    content.className = 'dvz_excel_grid';
    const render = (sheet) => {
        content.replaceChildren();
        const table = document.createElement('table');
        const tbody = document.createElement('tbody');
        for (const row of sheet.rows) {
            const tr = document.createElement('tr');
            for (const value of row) {
                const td = document.createElement('td');
                td.textContent = value;
                tr.append(td);
            }
            tbody.append(tr);
        }
        table.append(tbody);
        content.append(table);
        if (sheet.truncated) {
            const note = document.createElement('p');
            note.textContent = 'Preview limited to the first 500 rows and 80 columns. Download for the complete workbook.';
            content.prepend(note);
        }
    };
    for (const [index, sheet] of (data.sheets || []).entries()) {
        const tab = document.createElement('button');
        tab.className = `btn btn-sm ${index === 0 ? 'btn-primary' : 'btn-outline-secondary'}`;
        tab.textContent = sheet.name;
        tab.addEventListener('click', () => {
            for (const button of tabs.children) button.className = 'btn btn-sm btn-outline-secondary';
            tab.className = 'btn btn-sm btn-primary';
            render(sheet);
        });
        tabs.append(tab);
    }
    if (data.sheets?.length) render(data.sheets[0]);
    modal.append(header, tabs, content);
    overlay.append(modal);
    document.body.append(overlay);
    close.focus();
}

async function handleClick(event) {
    const target = event.target instanceof Element ? event.target : null;
    if (!target || !isExcel(target)) return;
    const card = target.closest('.o_attachment, .o-mail-Attachment, .o-mail-AttachmentCard, .o_AttachmentCard, [data-attachment-id]');
    const element = card || target;
    const id = attachmentId(element) || attachmentId(target);
    if (!id) return;
    // Explicit download controls retain their standard action.
    if (target.closest('[download], .o_attachment_download, .o-mail-AttachmentCard-download')) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    try {
        const result = await rpc(`/dvz_excel_preview/attachment/${id}`, {});
        if (result.error) {
            window.alert(result.error);
        } else {
            showPreview(result, id);
        }
    } catch (error) {
        console.error('Excel preview failed', error);
        window.alert('Preview is unavailable or you do not have access to this attachment.');
    }
}

document.addEventListener('click', handleClick, true);
