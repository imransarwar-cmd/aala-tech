# DVZ Material Reservations — Build and Test Report

Package: `dvz_material_reservation`  
Version: `19.0.1.0.0`  
Target: Odoo 19  
Build date: 17 November 2026

## Tests actually executed

**66 isolated regression tests: PASS.** They load the actual addon policy and stock-move adapter methods with a stubbed Odoo environment and stock engine. The suite also validates package structure, Python/XML syntax and internal references. These are not live Odoo/PostgreSQL/browser tests.

Coverage:

- Default and restricted reservation targets.
- Odoo 19's `force_qty` semantics: quantity to add, not total target.
- Zero targets and repeated assignment not taking released stock back.
- Stock shortages and subsequently available stock.
- Partial/full release with unchanged operation demand.
- Released quantity returned to a simulated available-stock ledger.
- Re-reservation to a new total target.
- Retained lot identity and mixed move-line/operation UoM conversion.
- Rejection of incompatible UoM precision, serial fractions, negative/over-demand targets.
- Rejection of picked and completed moves.
- Operation-group checks and rejection of forged boolean context bypasses.
- Reservation-history before/after values.
- Entire-package partial-release rejection and full-release behavior.
- Backorder cap allocation and capped move merge calculations.
- Direct move-line quantity changes that exceed a cap; controlled merge phase followed by validation.
- Manifest data paths, Python compilation/AST, XML parsing, local XML references, scoped ACLs, action/view presence and company rules.
- No direct stock-quant SQL updates, no SQL stock quantity writes, no transaction commits in the adjustment wizard.
- The standalone module does not depend on or modify the earlier DVZ SO locking addon.

The numerical-invariant test exercises many demand/target/split combinations; it is counted as one test, not inflated into thousands of separate tests.

## Additional validation

- Python compilation: PASS.
- XML well-formedness: PASS.
- Manifest parsing and file existence: PASS.
- ZIP CRC/integrity: PASS.
- The 66 checks were repeated after extracting the final ZIP: PASS.
- The alternative creator was run into a new temporary addons folder; the extracted file bytes match the ZIP. A second run refuses to overwrite the existing module.

## Not executed

- Live module installation/upgrade in an actual Odoo 19 registry.
- PostgreSQL stock quant behavior, SQL constraint execution and real concurrent reservation tests.
- Browser rendering/interaction and user-company record-rule enforcement in a live session.
- Interactions with the user's installed custom SO/project/stock/locking modules.
- Actual pick/pack/ship, manufacturing, MTO, package, barcode or return transactions.

Network/source-runtime installation was unavailable in the build container. No user server, database, or credentials were accessed. No claim of live deployment, real stock reservation, or production certification is made by this report.

## Supplied tests for a real Odoo test database

`tests/test_reservation.py` contains **20 post-install Odoo integration tests**, not executed here. They cover SO confirmation, manual customer-only reservations, partial/full release, re-reservation protection, shortages, competing orders, over-release rejection, picked/done protection, partial delivery/backorder targets, manual cancellation, refresh idempotency, audit protection, serial validation, project links, the native Unreserve button, permission denial and service exclusions.

Run ONLY against a disposable database after installing the normal dependencies:

```bash
python3 /PATH/TO/odoo-bin -c /PATH/TO/test.conf \
  -d YOUR_DISPOSABLE_TEST_DATABASE -i dvz_material_reservation \
  --test-enable --test-tags /dvz_material_reservation \
  --stop-after-init --no-http --logfile=/dev/stdout
```

Use the acceptance workflow in `README.md` with the user's installed custom addons before production use. Keep a database and code backup.
