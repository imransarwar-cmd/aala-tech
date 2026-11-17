# DVZ Sales Order Lock — strict-state regression report

Module: `dvz_sale_order_lock`  
Version: `19.0.1.2.0`  
Build date: 15 November 2026

## Source inspected

The exact prior attachment `dvz_sale_order_lock_v19.0.1.1.0.zip` was extracted
and inspected. This is an update of that same addon, not a replacement sales app.

The prior code deliberately bypassed Closed-order checks for the special group
and `env.su`. It computed read-only as `locked and not permitted` and returned
an empty native protected-field list for group members. The earlier tests even
expected group members to edit/create lines while Closed.

That confirms a mismatch with the requested strict Closed behavior. It does not
prove which groups or other customizations are active in the user's database.

## Before / after reproduction

Five updated guard regressions were executed against the original v1.1 code
using controlled ORM doubles:

1. Group-enabled creation of a line on a Closed SO must be rejected.
2. Group-enabled editing of a Closed SO line must be rejected.
3. Group-enabled deletion of a Closed SO line must be rejected.
4. The read-only helper must remain true for group members on a Closed SO.
5. Native protected fields must remain present for group members.

**Before: all 5 failed. After: all 5 passed.**

These are isolated method-level reproductions, not evidence from the user's
live database or a real browser renderer.

## Executed checks

**121 isolated regression tests passed.** They execute the actual addon guard
methods against ORM doubles, pure ContextVar policy helpers, and XML fixtures.
The entire suite was rerun after extracting the release ZIP.

Covered behavior:
- Ordinary, group-enabled and elevated explicit business writes are blocked.
- Closed SO line create/write/unlink, default parent IDs, mixed batches and
  reparenting in either direction are blocked before the mocked write mutates data.
- All 7 parent One2many command variants are rejected on Closed orders.
- Combined unlock plus header/line edits are rejected.
- A separate authorized reopen restores normal editing; reclosing blocks it.
- No browser/import/RPC context flag is an editing bypass.
- Custom SO/line fields, M2M selections and custom product attribute changes.
- Native protected-field behavior is not disabled for the special group.
- The complete order-line widget and nested line fields get readonly conditions.
- Native business readonly conditions are retained.
- Ribbon visibility, list-column placement, filters and grouping are retained.
- Narrow internal mail/portal metadata scopes do not permit business edits.
- Group XML IDs and view IDs remain stable.

Also checked: Python parsing/compilation, XML parsing, manifest data-file paths,
ZIP integrity, safe extraction paths, and package file structure.

## Tests NOT executed

The package includes **31 Odoo TransactionCase integration tests** in `tests/`.
They were updated for strict Closed behavior but were **not executed** here.

No real Odoo registry, PostgreSQL database, customer upgrade, browser rendering,
stock-delivery/invoicing end-to-end workflow, or third-party customization stack
was run in this build environment. No claim is made that all user-specific
custom workflows have passed. Run the acceptance checklist on staging.

The XML fixture applier is not Odoo's full view inheritance engine. The relevant
parent field, readonly rule and native protection methods were cross-checked
against the official Odoo 19.0 sources:

- https://raw.githubusercontent.com/odoo/odoo/19.0/addons/sale/models/sale_order.py
- https://raw.githubusercontent.com/odoo/odoo/19.0/addons/sale/models/sale_order_line.py
- https://raw.githubusercontent.com/odoo/odoo/19.0/addons/sale/views/sale_order_views.xml
- https://raw.githubusercontent.com/odoo/odoo/19.0/odoo/orm/fields.py
- https://raw.githubusercontent.com/odoo/odoo/19.0/addons/portal/models/portal_mixin.py

## Known consequences / boundaries

The former permission group is now a lock/reopen permission only. All previously
Closed orders stay Closed and become read-only for those users too. Existing
group membership is preserved because its XML ID is unchanged.

A workflow that creates or explicitly changes an SO line (including using sudo)
must reopen the order first. Native computed values may still recompute; this
is not a historical snapshot. Independent third-party child models or deliberate
SQL/ORM-bypassing server code are outside the module's guard boundary.

No sales data is deleted, no order is unlocked and no other addon is modified.
