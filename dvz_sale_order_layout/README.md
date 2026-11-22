# DVZ Sales Order Layout (Odoo 19)

Standalone add-on. Depends on `dvz_sale_project_naming` because it reuses the existing
`dvz_division_id` Department and replaces the existing `dvz_project_code` list column.

## Changes
- List: Creation Date, SO Date (`date_order`), Expiration Date (`validity_date`).
- List: existing Department remains; Project Code column is replaced by Analytic Code.
- Form: adds Order Dates and Order References groups on Other Information.
- Renames the displayed `amount_untaxed` label to `VAT` in list/form only. The value remains
  the untaxed amount, exactly as requested; no accounting calculation changes.
- Analytic Code: reads an existing `account.analytic.account` relation on the SO
  (`analytic_account_id`, `account_id`, or `analytic_id`), then optionally from the linked
  project. Displays analytic account `code` if available, otherwise its `name`.
- No analytic accounts are created; no SO, project, invoice or accounting data is modified.

## Install
Copy `dvz_sale_order_layout` into custom_addons, restart Odoo, update Apps List, install.
Upgrade after replacing code. Do not uninstall `dvz_sale_project_naming`.

## Important
The Sales Order analytic relation varies between databases. This module dynamically checks
the likely existing Many2one relations. If the Analytic Code is blank, the Sales Order has
no recognized direct analytic account or linked project analytic account. Inspect the
existing SO analytic field before adding any new relation.

## List-view Department correction (19.0.1.0.1)
The final combined Sales Order list architecture now removes any duplicate
`dvz_division_id` occurrences and inserts exactly one visible `Department`
column immediately after `user_id` (Salesperson). This does not alter the
field definition or stored values.

## Date columns correction (19.0.1.0.2)
The list view now guarantees Creation Date, SO Date and Expiration Date in that order.
An existing `date_order` field is explicitly relabelled `SO Date`; `create_date` is added
even when absent from the original Sales Order tree; `validity_date` is added/repositioned
immediately after it. Duplicate instances are removed from the final list architecture.
