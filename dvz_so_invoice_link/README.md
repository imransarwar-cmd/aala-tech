# DVZ Linked Invoices — Odoo 19

Adds a **separate Linked Invoices smart button** on the Sales Order form. Clicking it opens existing DVZ-referenced invoices, never the Create Invoice wizard.

- No XML view files: view is registered by the Python model `init()` method when the module is installed/upgraded.
- Preserves existing `dvz_linked_invoice_ids` Many2many data and its relation table.
- Does not modify sale order lines, invoice lines, totals, payments or accounting entries.
- Leaves Odoo's standard Create Invoice and Invoices buttons unchanged.
- The new button is shown to Sales users, including when the count is zero.

Upgrade: replace existing `dvz_so_invoice_link` directory, restart Odoo, then upgrade the module from Apps. No need to rerun invoice linking script.

**Test on staging before production.** Odoo registry/view validation has not been run in this environment.
