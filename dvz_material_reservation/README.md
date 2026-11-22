# DVZ Project & Customer Material Reservations

**Technical name:** `dvz_material_reservation`  
**Odoo:** 19.0  
**Version:** 19.0.1.0.0  
**Purpose:** Reserve real available warehouse materials against a confirmed Sales Order, project/analytic project, or customer-only manual request. Release all or a specified quantity without changing the SO demand.

## Important validation status

The package has passed Python/XML/package validation and **66 isolated regression tests**. These tests use a stubbed ORM/stock engine for the adapter methods; they are **not** a live Odoo installation or PostgreSQL/browser test. Twenty Odoo integration tests are supplied but could not be run in the build environment, which has no Odoo/PostgreSQL runtime. Validate on a disposable copy of your database before production installation. No connection to your servers has been made and no business records have been changed.

## What is implemented

- An independent extension: no edits to original Odoo or other custom-addon files.
- Confirmation of an SO creates one reservation register entry and attempts to reserve its existing stock operations.
- Uses native stock moves/move lines and stock reservation APIs; no second fake quantity table and no direct writes to `stock.quant.reserved_quantity`.
- Only inventory-tracked products (`is_storable`) and internal-source warehouse stock operations qualify. Services and untracked consumables are excluded.
- Existing customer, SO, warehouse and typed project/analytic links are reused where unambiguous.
- New customer/project manual holds use the separate **Reservation Register** form. They can be linked to a customer and optional project, with an optional typed Project Reference. They create a normal **unvalidated outgoing transfer** from the chosen internal source.
- Per-operation release, multi-selection release, release all for a document, and bulk release for filtered project/customer documents.
- A persistent total reservation limit prevents “Check Availability” and standard `_action_assign` jobs from immediately re-reserving a released quantity.
- “Set Reservation Target” raises/lowers the total permitted reservation; “Reserve Available” fills only the existing target.
- The native transfer **Unreserve** action also sets the managed operations’ limits to zero and records the release.
- Original SO ordered quantity and stock move demand remain unchanged by reservation adjustments.
- Standard deliveries and backorders remain Odoo operations. Backorder caps use the remaining allocation, not a duplicate copy of the entire previous limit.
- No automatic validation, invoice posting, delivery costing, stock valuation, SO locking or payroll changes.
- Audit entries include actor, time, product, unit, before/after reserved quantities and reason. They cannot be manually edited/deleted through this addon.
- No buttons or extra fields are added to the Sales Order form. Automatic reservation runs after SO confirmation. Project and Analytic Account reservation views retain their own navigation. Dedicated register/line views have customer/project/SO/product/location/status filters and grouping. Native Odoo list export is available under your existing export permissions.

## Installation — new addon

1. Back up the test database and put this folder directly inside the active Odoo 19 `addons_path`:
   `custom_addons/dvz_material_reservation/__manifest__.py` must exist.
2. Ensure Sales, Inventory, Project and Analytic dependencies are available. The manifest declares `sale_stock`, `project`, `analytic`, `mail`.
3. Restart the **actual instance** you are testing; do not restart an unrelated Odoo service.
4. Developer mode → Apps → Update Apps List → remove the Apps filter → search **DVZ Project & Customer Material Reservations** → **Install**.
5. Do not uninstall or replace `dvz_sale_order_lock`, the quantity-summary addon, or the Honeywell delivery-cost addon.

For a disposable local database, with the normal Odoo virtual environment activated, an example command is:

```bash
python3 /PATH/TO/odoo-bin -c /PATH/TO/odoo.conf \
  -d YOUR_TEST_DATABASE -i dvz_material_reservation \
  --no-http --stop-after-init --logfile=/dev/stdout
```

Run the command as the normal Odoo OS user. Stop concurrent workers for that same test database while installing. `--no-http` avoids a second HTTP listener; it does not make concurrent schema updates safe. This is a **new module**, so `-i` is for first installation, `-u` for later upgrades.

### Permissions

The new group is **Material Reservations / Manage Reservations / Release Stock** (technical ID `dvz_material_reservation.group_reservation_operator`). Assign it only to authorized warehouse staff. It implies Inventory User. Inventory Administrators inherit it automatically. Sales users can read reservations permitted by their company/document rules but are not automatically given release permission.

Native Inventory ACLs still apply. This addon is an operational reservation tool, not an absolute security barrier against an Inventory Administrator performing unrelated manual stock operations.

### Automatic reservation and the existing project field

Inventory → Configuration → **Reservation Settings** (active company).

- Automatic reservation is enabled by default for future SO confirmations.
- Turning this option off stops this addon’s automatic register/refresh logic; it does **not** disable Odoo's independent native operation-type reservation setting.
- **Existing SO Project / Analytic Field** maps a real Many2one field already on `sale.order` to a typed Project/Analytic link.
- **Existing SO Project Reference (Text)** maps your existing Sales Order Char field (for example, a project code/reference) to `project_reference` on the reservation. It is displayed on the reservation list and form for reference only. Select the exact Char field in Reservation Settings; no duplicate field is created on the SO.
- Without a mapping, the addon checks unambiguous native `project_id`, `analytic_account_id`, `project_ids`, then the already-installed optional naming link `project.project.dvz_origin_sale_id`.
- A plain text field called `project` is not assumed to identify a `project.project` or `account.analytic.account` record.
- No project or analytic account is created, no project name is matched, and no duplicate SO project selector is added.
- An absent/ambiguous project does **not** stop customer/SO stock reservation. The register shows a message; an authorized user can select Project/Analytic Project on the reservation itself.
- Reservations are one document per SO. An SO split across several projects must be handled explicitly; this version does not guess line-level multi-project allocations. Use separate SOs/reservations when project ownership differs.

## Workflow A — materials for a Sales Order/project

1. Set the existing SO project/analytic field, customer, warehouse and material lines.
2. Confirm the SO.
3. Open **Inventory → Material Reservations → Reservation Register** and filter by the Sales Order.
4. Review each operation’s demand, actual reserved quantity, target, shortage and released/on-hold quantity.

The addon reserves **available stock only**. For example, demand 10 and free stock 6 gives Reserved 6 and Waiting for Stock 4; it never claims that all 10 are physically reserved.

Existing confirmed SOs are not mass-modified during installation. An authorized user can open an existing SO and click **Refresh Material Reservations** to attach its existing operations and attempt reservation. This action is deliberate and can reserve available stock. It preserves any existing per-operation release limits.

## Workflow B — manual customer hold without any project/SO

Inventory → Operations → Material Reservations → **Reservation Register** → New.

Enter Customer, Delivery Address, Company, Warehouse, Manual Hold Source, and the products/quantities. Project and Analytic Project are optional. Click **Confirm & Reserve**.

This creates one unvalidated customer transfer from the selected internal source. It reserves stock; it does not physically move stock or create an invoice. Open **Transfers** to issue the goods later through the usual Inventory process. Manual requests use each product's base UoM.

A manual hold does **not** automatically become an allocation on a later SO for the same customer. It is a separate outgoing demand. Do not also confirm a second demand for the same material expecting it to consume that hold automatically: issue using the manual transfer, or deliberately release/cancel it before reserving a new SO.

## Workflow C — release a specific quantity

Open **Reservation Lines** or a reservation's **Reservation Lines** smart button. Use Release on a single row, or select several rows and **Release Selected**.

Example: demand 10, currently reserved 10. Enter release quantity **3**, provide a reason, then Apply.

- Reserved becomes **7**.
- SO ordered quantity and operation demand remain **10**.
- Reservation target is now **7**.
- The released 3 become available to other reservations.
- Check Availability does not take those 3 back for this operation.

The release action sets the target to the **current reservation minus released quantity**, not “demand minus release”. For demand 10, current reservation 4 and release 2, the target becomes 2. The other 8 are now on hold, including the previously unfilled demand. This intentionally stops immediate re-reservation. Raise the target explicitly when you want future stock allocated again.

Rows entered as zero in the release wizard are skipped. Changes are one Odoo transaction: if a selected row fails validation, the operation raises an error and is rolled back.

## Workflow D — full release for an SO or project/customer

For one reservation, click **Release / Unreserve**, select **Release all and stop automatic re-reservation**, enter a reason, Apply.

For all reservations of a project/customer, filter the **Reservation Register**, select the intended entries, click **Release Selected Reservations**, then use Release all. Or filter/select their open lines in **Reservation Lines**. Process one company at a time.

This also sets the target to zero on open operations that currently have no reserved stock, preventing later availability from automatically refilling them. It does not cancel the SO, reduce demand, delete history or reverse an already completed delivery.

## Workflow E — reserve again

Use **Set Reservation Target**, enter the **new total target** (not an additional quantity), provide a reason, Apply. Example: existing reservation 7, new total target 10 → attempt to reserve an additional 3 if stock is available.

**Reserve Available** never raises a zero/reduced target. It only fills stock shortages up to the target already approved. A cap cannot exceed the operation demand; over-allocation is rejected.

## Report columns

| Column | Meaning |
|---|---|
| Reservation, SO, Customer, Project, Analytic Project | Real linked records, not name matching |
| Operation Demand | Native stock move demand for this route stage |
| Reserved Qty | Current reserved/assigned quantity on an unfinished move |
| Reservation Target | Maximum approved current reservation, bounded by demand |
| Waiting for Stock | Max(target − reserved, 0) |
| Released / On Hold Qty | Demand minus target; **not a cumulative release-event total** |
| Unit | This operation's UoM |
| Transfer, source and destination | Native warehouse/route stage |
| State | Native move state |

No single meaningful total is assumed for mixed units. In pick/pack/ship routes, the same product appears at several route stages; do not add those demands together as one SO quantity. Filter a transfer/stage and group by product/unit for quantities. Completed operations show zero *current reservation*; inspect the native transfer for what was delivered. Audit events preserve release history.

Use Odoo's standard list selection → Actions → Export, or the list export icon where available, to download the selected breakdown as XLSX/CSV according to your version and user permissions.

## Safety and scope

- This is actual stock reservation, not physical project-bin segregation or ownership accounting.
- It never steals another move's reserved stock. It uses the native available-stock reservation engine.
- Normal lots/serials/owners/locations are preserved by the ORM. Native removal strategy chooses reservation lots. Partial release removes the last unprocessed move lines first; no per-lot selection wizard is added.
- Serial-tracked quantities must be whole units. Whole/result packages must be unpacked using Inventory before partial release; full unreserve is supported.
- Picked operations cannot be adjusted here. Completed/cancelled moves cannot be released. Use normal return/correction workflows for goods already delivered.
- A native stock move shared ambiguously by several SOs is not assigned to two reservations; conflicting links are rejected for review.
- Multi-step stock route operations are associated through real move links. MTO waits for its native upstream supplies. Supplier-to-customer dropshipping and manufacturing consumption are not treated as internal customer stock reservations.
- Manual customer holds are direct outgoing transfers from the selected internal location, not automatic pick/pack/ship route construction.
- Raising targets and full/partial releases requires the new operator group. Native stock actions and other custom addons still have their existing access rules.
- The addon does not validate an individual delivery line for you. Deliver selected quantities using native partial validation/backorders.
- No expiry scheduler, automatic purchasing, automatic reassignment of holds between SOs, or mass legacy-reservation migration is added.
- Before uninstalling, review/release/cancel outstanding manual holds. Their native transfers are business documents; uninstalling must not be used as a stock-reversal procedure.

## Acceptance test — test database only

Use an inventory-tracked product with 20 units available in the test warehouse.

1. Confirm Project A SO for 10. Expect one reservation and 10 reserved; no duplicate outgoing move.
2. Release 3. Expect 7 reserved, demand still 10, release event with before 10 / after 7.
3. Click Check Availability / Reserve Available. Expect 7, not 10.
4. Create another customer hold for 5 without a project. Expect 5 reserved and an unvalidated transfer.
5. Release all Project A reservation. Expect target/reserved zero, SO still confirmed and demand unchanged.
6. Set Project A target to 4. Expect 4 reserved if stock remains available.
7. Attempt release of 5 when only 4 is reserved. Expect rejection with no stock changes.
8. Mark an operation Picked and try release. Expect rejection.
9. Validate a real partial delivery normally; inspect the backorder. Caps must not duplicate the original limit.
10. Test company isolation and ordinary warehouse/sales users separately from the operator/administrator.
11. Test your project's exact existing SO field mapping and your installed custom route/lock modules before deployment.

### Supplied Odoo integration tests

Twenty tests in `tests/test_reservation.py` are intended for a **disposable** database. They have not been run in the build environment:

```bash
python3 /PATH/TO/odoo-bin -c /PATH/TO/test.conf \
  -d YOUR_DISPOSABLE_TEST_DATABASE -i dvz_material_reservation \
  --test-enable --test-tags /dvz_material_reservation \
  --stop-after-init --no-http --logfile=/dev/stdout
```

Do not run integration tests against `aala_tech_production`.

### Offline regression checks

`python3 qa/test_isolated.py` (requires `lxml` only for XML checks) runs isolated adapter/policy/package tests. Passing these checks cannot substitute for testing real Odoo ORM behavior, PostgreSQL locks, custom-addon interactions, or browser layouts.

## Official Odoo 19 reference interfaces reviewed

- `addons/stock/models/stock_move.py`: `_action_assign(force_qty=False)`, `_do_unreserve`, stock move split/merge and `product_uom`.
- `addons/stock/models/stock_move_line.py`: `quantity`, `product_uom_id`, serial/package fields and ORM stock synchronization.
- `addons/sale_stock/models/sale_order_line.py`: `_action_launch_stock_rule(*, previous_product_uom_qty=False)` and native move links.
- `addons/sale_stock/models/sale_order.py`: SO confirmation/delivery lifecycle.
- Native Sales, Project and Analytic Account button-box anchors, and Odoo 19 `res.groups.privilege` security layout.

The module is LGPL-3 licensed. Source and tests are included.


## Consolidated package and UI scope

This package contains only the `dvz_material_reservation` addon. The uploaded archive also contained separate `dvz_material_auto_reserve`, `dvz_material_manual_reserve`, `dvz_material_reservation_view`, and `dvz_material_reservation_refs` addons that duplicate or overlap this module's automatic SO confirmation hook, manual reservation form, and reservation register. Do not install those parallel addons for this workflow. If any are already installed, review their dependencies and existing records before uninstalling them; this package does not automatically uninstall other modules.

No button, smart button, or refresh action is added to the Sales Order form. Automatic stock reservation is performed by the existing `sale.order.action_confirm()` hook when the company setting is enabled. Manual customer/project reservations are created from Inventory > Material Reservations > Reservation Register.

The Sales Order project text reference is configured under Inventory > Configuration > Reservation Settings by selecting the exact existing `sale.order` Char field. The selected value is copied into the reservation's `Project Reference` field at confirmation. This is a reference only; the typed Char value does not create or infer a `project.project` record.
