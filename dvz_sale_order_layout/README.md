# DVZ Sales Order Layout (Odoo 19)

Standalone add-on. Depends on `dvz_sale_project_naming` because it reuses the existing
`dvz_department_ids` Department and replaces the existing `dvz_project_code` list column.

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
`dvz_department_ids` occurrences and inserts exactly one visible `Department`
column immediately after `user_id` (Salesperson). This does not alter the
field definition or stored values.

## Date columns correction (19.0.1.0.2)
The list view now guarantees Creation Date, SO Date and Expiration Date in that order.
An existing `date_order` field is explicitly relabelled `SO Date`; `create_date` is added
even when absent from the original Sales Order tree; `validity_date` is added/repositioned
immediately after it. Duplicate instances are removed from the final list architecture.

## Quotation form parity (19.0.1.0.3)
Odoo Quotations and confirmed Sales Orders are both `sale.order` records and use the
same standard form architecture. The final form architecture now guarantees the
existing Department field `dvz_department_ids` immediately after Salesperson (`user_id`)
for both states, while retaining the Order Dates and Analytic Code groups.

## Department field correction (19.0.1.0.4)
The correct existing Department field is `dvz_department_ids` (Many2many), not
`dvz_division_id` (Many2one). Both the list and form layouts now use
`dvz_department_ids` with the `many2many_tags` widget immediately after Salesperson.
Any obsolete `dvz_division_id` occurrence is removed from the final view architecture.
No field is created, no department relations are changed, and no database data is migrated.

## Always-visible form dates (19.0.1.0.5)
Creation Date, SO Date (`date_order`) and Expiration Date (`validity_date`) are now
inserted in an always-visible Order Dates group on the main Sales Order/Quotation form,
immediately before the notebook tabs. They are no longer placed only under Other Information.

## Duplicate SO Date after Expiration Date (19.0.1.0.6)
The main form Order Dates group displays Creation Date, SO Date, Expiration Date,
and a second read-only SO Date field immediately after Expiration Date, as requested.
Both SO Date fields reference the same native `date_order` value; no new stored field
or database migration is created.

## Form date layout correction (19.0.1.0.7)
Removed the custom Order Dates section entirely. The form now adds exactly one
read-only `date_order` field labelled SO Date immediately after the existing
`validity_date` field. Existing native Creation Date and SO Date fields elsewhere
in the form are not duplicated or modified.

## Restore Department before System on form (19.0.1.0.8)
The form architecture now preserves/reuses the existing `dvz_department_ids`
Many2many field and places it immediately before the System field (`system_ids`
or `system_id`). It no longer places Department after Salesperson on the form.
The list-view behavior remains Department after Salesperson. No Department values
or relationships are modified.

## Restore the actual Department field before System (19.0.1.0.9)
Inspection of the original uploaded `dvz_sale_project_naming` source confirms the
existing Department field on `sale.order` is `dvz_division_id` (Many2one) and the
System field is named `system`. This version uses that actual field when present,
inserts it immediately before `system`, and uses the Many2many `dvz_department_ids`
only if that field is genuinely installed in the registry. The list view uses the
same detected field after `user_id`. No data or relationships are changed.

## Optional list columns and order (19.0.1.1.0)
The Sales Order/Quotation list includes Creation Date, SO Date, Expiration Date,
Analytic Code, Department and the existing amount_untaxed column labelled VAT.
These added columns are `optional="hide"` so users can enable them from the list
view optional-columns menu. Analytic Code is positioned immediately before
Department; Department is immediately after Analytic Code and both follow Salesperson.
The VAT label changes only the caption; the underlying amount remains untaxed.

## List column visibility update (19.0.1.1.1)
SO Date, Analytic Code, Department and the existing `amount_untaxed` column labelled
VAT are visible by default (`optional=show`). Activities fields (`activity_ids`,
`activity_state`, `activity_date_deadline`) are hidden by default (`optional=hide`).
Expiration Date remains available as an optional hidden column. The VAT caption still
maps to the original untaxed amount value; no accounting calculation is changed.
