# Chatter Excel Preview — Odoo 19

Version: **19.0.1.0.0**  
Technical name: `dvz_chatter_excel_preview`  
License: LGPL-3.0-or-later  
Deployment: self-hosted Odoo 19 backend. Uses community `mail` and `web` APIs; no Enterprise-only module is required. Live compatibility with a particular Community/Enterprise installation still requires staging validation.

## What it does

Click an existing `.xlsx`, `.xlsm` or `.csv` attachment card in chatter. A read-only worksheet dialog opens inside Odoo. It includes visible-sheet tabs, row/column headings, 100-row paging, simple cell formatting, fully contained merged cells, in-page search highlighting, wrap-text control, zoom, expand, cell selection, and **Download original**.

It reuses the native chatter attachment click; no top-of-form smart button, extra business field, menu, record creation or database migration is added. The native tile's Download/Remove actions are retained. Other file types retain Odoo's existing behavior. Where the same native AttachmentList is used elsewhere in the backend, the patch also applies there; custom attachment widgets are not automatically covered.

Existing attachments work without re-uploading. Your project naming, project security, SO–invoice linking and internal transfer add-ons do not need replacement.

## Installation

1. Back up the database and filestore. Test on a staging clone first.
2. Extract the ZIP. Place **the `dvz_chatter_excel_preview` folder** directly inside a directory in your Odoo `addons_path`. Do not nest it an extra level.
3. Ensure the dependencies in `requirements.txt` are installed in the Python environment used by the Odoo service. Odoo's published requirements already include openpyxl; do not blindly upgrade it. `defusedxml` may need adding. An illustrative command, using your actual environment path:

   ```bash
   /path/to/odoo-venv/bin/python -m pip install -r /path/to/custom-addons/dvz_chatter_excel_preview/requirements.txt
   ```

4. Restart all Odoo application workers. Enable developer mode and select **Apps → Update Apps List**.
5. Remove the default **Apps** search filter if needed, search **Chatter Excel Preview**, and install.
6. Hard-refresh the browser. Open a saved record with chatter, attach an Excel file or use an existing file, wait for upload completion, and click its attachment card.

This is a new standalone add-on, not an update to any previous add-on. For future versions, replace this same folder, restart, and upgrade this module. Do not uninstall earlier modules.

## Security design

- The public ORM method accepts only the current attachment record ID, a visible-sheet index and a fixed page offset. It does not accept a filename/path, raw bytes, arbitrary record model, external URL, domain or access token from the browser.
- Internal users only; portal/public preview is not exposed by this add-on.
- On **every page/sheet request**, the method calls `ir.attachment.check_access('read')` and explicitly checks the linked parent record's read access before reading file bytes. There is no `sudo()` in the add-on's preview method. A public attachment does not bypass this extra parent check.
- No ACLs or record rules are added or relaxed. Existing project/task access restrictions must be validated with your actual installed security add-ons on staging.
- No write operations or persistent preview cache, no generated public attachments, no third-party conversion service, no macros, no formula evaluation and no hyperlink navigation.
- Cell content is sent as plain data and rendered with Owl `t-esc`. Styling uses a strict whitelist rather than arbitrary workbook HTML/CSS.
- ZIP entry/size/expansion checks, XML DTD/entity rejection, XML node limits and bounded output help limit parser resource use. These are safeguards, not a substitute for maintained dependencies and Odoo worker time/memory limits. Concurrent requests and time inside third-party library calls remain subject to server limits.
- Already-delivered data cannot be revoked from a user's browser. A later failed permission check clears the preview's previous page, and reopening/paging checks access again.
- The existing Odoo Download action is not modified; existing public links or already-downloaded files are outside this module's scope.

## Formats and limitations

| Item | Behavior |
|---|---|
| `.xlsx` | Genuine OOXML workbook, read-only preview |
| `.xlsm` | Worksheet data only; VBA content is never executed |
| `.csv` | UTF-8, UTF-8 BOM or UTF-16 BOM; comma/semicolon/tab/pipe detection; values stay text |
| `.xls`, `.xlsb`, `.ods` | Not intercepted; use native download. Save as `.xlsx` to preview |
| Encrypted/password-protected workbook | Not supported; a clear error is shown |
| Formula result | Saved cached value, which may be stale; **never recalculated** |
| Formula without saved value | Formula text or an explicit no-saved-result label |
| Formatting | Bold, italic, underline, RGB/indexed colours, fill, alignment, wrap, basic numeric/percentage formats |
| Date/time | Stable ISO display, not locale-identical Excel display |
| Merged cells | Only when the full merged range lies within the current page and visible columns |
| Hidden sheets/rows/columns | Omitted. Hidden content is not a security boundary; authorized users can still download the workbook |
| Charts, pictures, pivot layouts, conditional formatting, theme tints, advanced formatting | Not reproduced; preview is not pixel-perfect Excel |
| Editing/saving back | Not available; the attachment remains unchanged |
| Search | Current loaded page only, not the entire workbook |
| Custom widgets / customer portal | Not covered by this backend chatter integration |

## Fixed preview limits

- File: **10 MiB** (10,485,760 bytes).
- Workbook: at most **100 worksheets**.
- Worksheet: first **5,000 rows and 100 columns**, paged by **100 rows**.
- Long text: at most **2,000 characters per cell** and **500,000 characters per page**; truncation is stated in preview notes.
- ZIP: at most 2,000 entries, 24 MiB per expanded entry, 64 MiB total expanded size, and a 200:1 compression limit for entries over 1 MiB.
- XML: at most 600,000 end elements; DTDs/entities are rejected before workbook loading.
- Cooperative parsing deadline: 12 seconds, supplemented by your Odoo worker limits. This is not a hard preemptive deadline inside library functions.

Preview notes show truncation and simplifications. The original download remains complete and unchanged. For CSV, a reported row count of 5,001 means "at least 5,001" because scanning stops at that limit.

No server-side cross-user cache is introduced. Reopening a sheet or changing page re-reads the attachment and checks rights again; large workbooks may be slower.

## Validation status

**Executed in this build environment:** 46 Python tests (34 real parser tests and 12 RPC-method tests with test doubles), 14 JavaScript tests with test doubles, Python compilation, JavaScript syntax checks, XML parsing, CSS parsing and package validation. Parser tests used openpyxl 3.1.5 and defusedxml 0.7.1. JavaScript tests ran on Node.js 22.16.0.

**Not executed:** Odoo installation/upgrade, real ORM record-rule tests, Owl template compilation/mounting, real backend browser navigation, or checks against your installed modules. No Odoo server/database was available. The 8 database integration tests in `tests/` are supplied for staging and are NOT part of the passed offline count.

Run offline checks from this module folder:

```bash
python -m unittest discover -s tests_offline -p 'test_*.py' -v
node --test tests_offline/test_frontend.mjs
```

Example staging integration run (use real paths, credentials and a disposable staging database):

```bash
/path/to/odoo-bin -c /path/to/staging.conf -d STAGING_DATABASE \
  -i dvz_chatter_excel_preview --test-enable \
  --test-tags /dvz_chatter_excel_preview --stop-after-init
```

Use `-u` rather than `-i` when already installed. The supplied integration suite tests parent/attachment permissions, portal denial, no mutation, and external-link rejection. It does not replace browser acceptance testing.

### Staging acceptance checklist

Open the same test file as an HOD, the assigned project manager, a task-only assignee and an unrelated user. Confirm that the preview honors the same parent-record visibility intended by your project-security rules. Also test attachments to another permitted company and a non-permitted company.

Test a two-sheet XLSX, a real BOQ XLSM, CSV, long rows, an attachment above 10 MiB, a locked/corrupt workbook and a formula with/without a saved result. Verify normal PDF/image viewing, download/remove, mobile actions, Escape/Close, repeat clicks, expanding, paging and a hard-refresh after deployment. Confirm file checksum is unchanged.

## Troubleshooting

**Cannot install: dependency missing.** Install the named Python package in the Odoo service's environment, not an unrelated system Python. Restart the service afterward.

**Click still downloads or opens the old viewer.** Confirm this module is installed in the correct database, hard-refresh, and inspect `?debug=assets` in staging. Another customization may replace the native AttachmentList click handler; code review is required in that case.

**Access denied but a tokenized download works.** This preview intentionally does not accept public/share tokens or bypass linked-record rules. Correct the record's legitimate permissions rather than granting broad access or adding `sudo()`.

**Some cells look different from Excel.** This is a bounded data preview. Use Download original for exact workbook layout, charts, advanced formatting and formula recalculation.

**File is too complex.** Use Download original. Do not disable safety limits without a capacity/security review.

## Primary references used for API verification

- Odoo 19 AttachmentList: https://raw.githubusercontent.com/odoo/odoo/19.0/addons/mail/static/src/core/common/attachment_list.js
- Odoo 19 attachment card template: https://raw.githubusercontent.com/odoo/odoo/19.0/addons/mail/static/src/core/common/attachment_list.xml
- Odoo 19 Dialog: https://raw.githubusercontent.com/odoo/odoo/19.0/addons/web/static/src/core/dialog/dialog.js
- Odoo 19 dialog service: https://raw.githubusercontent.com/odoo/odoo/19.0/addons/web/static/src/core/dialog/dialog_service.js
- Odoo 19 attachment checks: https://raw.githubusercontent.com/odoo/odoo/19.0/odoo/addons/base/models/ir_attachment.py
- Odoo 19 requirements: https://raw.githubusercontent.com/odoo/odoo/19.0/requirements.txt
- openpyxl read-only mode: https://openpyxl.readthedocs.io/en/stable/optimized.html
- openpyxl XML security guidance: https://openpyxl.readthedocs.io/en/stable/
