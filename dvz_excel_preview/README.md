# DigitalVizta Excel Attachment Preview (Odoo 19)

Adds read-only Excel preview for standard attachment cards/links in the Odoo backend, including chatter. Supports `.xlsx` and `.xls`, with worksheet tabs and an explicit Download action.

## Installation
1. Install Python dependencies into the **Odoo server's** Python environment: `pip install openpyxl xlrd`.
2. Copy `dvz_excel_preview` into a configured Odoo addons path.
3. Restart Odoo, update Apps list, install **DigitalVizta Excel Attachment Preview**.
4. Hard-refresh browser (or test with `?debug=assets`).

## Notes
- Does not edit uploaded files. Preview uses the current user's attachment read permission; no `sudo()`.
- Limits preview to 12 MB, 30 sheets, 500 rows and 80 columns per sheet; original remains downloadable.
- Displays values, not full Excel formatting, charts, formulas or macros.
- The listener targets standard Odoo 19 backend attachment markup. Third-party custom attachment widgets or nonstandard routes may need selectors adapted.
- **Test on Odoo 19 staging before production.** Odoo 19 mail UI markup and click handling may differ by build; integration has not been validated against a running Odoo instance.
