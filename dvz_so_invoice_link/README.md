# DVZ SO Invoice Reference Link (Odoo 19 Community)

Adds an independent many-to-many reference from Sales Orders to existing customer invoices. Extends the existing **Invoices** smart button count and action to include manually referenced invoices. It does **not** modify `account.move.line.sale_line_ids`, Sales Order lines, journal entries, invoice amounts, or the Sales Order's invoicing status.

## Installation
1. Copy `dvz_so_invoice_link` to your addons path.
2. Restart Odoo, update Apps List, install **DVZ Sales Order Invoice Reference Link**.
3. Set ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD in your environment.
4. Run `python3 dvz_link_invoices.py --test-one ATC/INV/2026/00350` (dry run).
5. Run the same command with `--apply` after checking the dry run.
6. Use `--all --apply` only after validating on staging.

CSV headers: `Number,SO #`. Default CSV is `invoice_so_mapping.csv` next to the script.

## Caveats
- Test against your exact Odoo 19 build on staging before production.
- This addon is a **display/reference** link only; Odoo's standard invoiced quantity, invoice status and down payment calculations remain unchanged.
- No changes to the standard invoice record, Sales Order amount or existing accounting lines are performed by the script.
- Standard record rules continue to apply to invoice visibility.
