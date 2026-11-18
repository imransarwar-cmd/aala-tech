# DVZ Project Delivery Costing

Version: **19.0.1.9.0** — Odoo 19 Community

## Fully generic technical identity

| Item | Name |
| --- | --- |
| Addon directory and technical module name | `dvz_project_delivery_cost` |
| Display name | DVZ Project Delivery Costing |
| Menu | Project → Configuration → Project Delivery Costing |
| Effective analytic-account flag | `dvz_project_delivery_costing` |
| Scope setting | `dvz_project_delivery_costing_scope` |
| Selected accounts setting | `dvz_project_delivery_costing_account_ids` |
| Scope parameter | `dvz_project_delivery_cost.scope` |
| Selected-account parameter | `dvz_project_delivery_cost.analytic_account_ids` |
| Existing cost-line model | `dvz.project.delivery.cost.line` |

The addon folder, Python field names, XML identifiers, configuration keys,
menu, settings, and descriptions use generic project terminology. The
settings window uses Odoo 19's supported `current` action target.

## Configuration

As a Settings administrator, open:

**Project → Configuration → Project Delivery Costing**

Choose one option, then click **Save**:

| Option | Behavior |
| --- | --- |
| All Projects | Enable delivery costing for every analytic account, including accounts created later. |
| None | Stop delivery costing synchronization and hide the Delivered Cost smart button. Retain existing cost lines. |
| Selected Projects | Show a Many2many field of analytic-account names. Select one or more accounts. |

The configuration applies globally, matching the original per-account
checkbox scope. Odoo's existing analytic-account access rights apply to the
picker. A separate `project.project` record is not required.

Saving a changed configuration synchronizes existing completed customer
deliveries for newly enabled accounts. Removing an account or choosing None
does not delete historical cost lines. Switching to All or None retains the
selected list so it can be reused later.

## Existing costing behavior retained

**Delivered Cost = Sales Order line unit price × actual completed customer
delivery quantity.**

The matching and calculation rules are unchanged:

1. Match Sales Order lines through their `analytic_distribution`.
2. Keep the fallback to existing `analytic_account_id`, `account_analytic_id`,
   or `analytic_id` fields on Sales Orders.
3. Use completed moves with a customer destination and positive quantity.
4. Convert delivered quantity to the Sales Order line's unit of measure and
   convert unit price to company currency where required.
5. Keep the original 100% allocation rule and one line per analytic account
   and stock move. Synchronization updates existing lines.

Partial deliveries, backorders, delivery validation, and the Delivered Cost
smart button retain their existing processing. Stock valuation, product
standard cost, discounts, and taxes are not introduced into the calculation.

## Fresh installation

Use these steps only if an earlier delivery-costing addon has never been
installed in this database:

1. Extract the `dvz_project_delivery_cost` folder into your configured addons
   directory.
2. Restart Odoo, refresh the Apps List, and install **DVZ Project Delivery
   Costing**. Remove the Apps-only filter if the addon is not listed.
3. Open the configuration menu and choose the required scope. The initial
   setting is None.

The existing custom dependency `dvz_project_purchase_report` must be present.

## Rename an existing installation without uninstalling

Changing the addon directory also changes Odoo's technical module identity.
The included script renames the existing database metadata before the new
addon is loaded, preserving the cost-line model/table, records, and saved
scope selections. The normal module upgrade then loads the generic source.

**Do not uninstall the existing addon or install a second copy.** The new
addon's installation hook stops a parallel installation when an earlier
addon still owns the cost-line model.

1. Back up the database and stop the normal Odoo process.
2. Place the new `dvz_project_delivery_cost` directory in the configured addons
   path. Move the previous addon directory outside all configured addons
   paths. Do not refresh the Apps List before completing the rename.
3. If another custom addon's manifest, imports, or XML explicitly refers to
   the previous technical module name, update that source reference to the
   new generic name. Database migration cannot rewrite external source files.
4. Make the official Odoo upgrade utilities available in the same Python
   environment that runs Odoo. If they are not already installed:

   ```bash
   python3 -m pip install git+https://github.com/odoo/upgrade-util@master
   ```

5. Run the following from your Odoo source directory, using your actual config,
   database, and absolute addon path:

   ```bash
   python3 odoo-bin \
     -c /path/to/odoo.conf \
     -d YOUR_DATABASE \
     -u dvz_project_delivery_cost \
     --pre-upgrade-scripts=/absolute/addons/dvz_project_delivery_cost/scripts/rename_existing_module.py \
     --stop-after-init \
     --no-http
   ```

6. After the command completes successfully, restart Odoo normally and open
   **Project → Configuration → Project Delivery Costing**.

The migration detects the existing addon from ownership of
`dvz.project.delivery.cost.line`; it does not require you to type the old
module name. It checks for conflicting metadata and requires the official
upgrade utility package before making changes. If a conflicting target module
already exists, it stops instead of merging unrelated installations.

The original module's installed version is preserved during the rename. For
an earlier checkbox-only installation, the retained `19.0.1.8.0` upgrade
scripts transfer enabled accounts, including archived accounts, into Selected
Projects. For an installation already using scope settings, those saved
settings are preserved without copying stale values from an old Boolean
column. Existing cost lines are not recalculated or deleted by the rename.

The `--pre-upgrade-scripts` command is needed once for an existing installation.
Subsequent versions upgrade normally under `dvz_project_delivery_cost`.

## Dependencies

- `base_setup`
- `project`
- `dvz_project_purchase_report`
- `sale_stock`
- `stock_account`
- `analytic`

`odoo.upgrade.util` is used only by the one-time external rename helper; it is
not required for ordinary operation or a fresh installation of this addon.

## Verification and limits

The package is checked for generic naming, Python syntax, XML references,
Odoo 19 action-target compatibility, preservation of calculation logic, and
ZIP integrity. Local simulated checks do not replace a live PostgreSQL/Odoo
upgrade. Run the rename on a copy of the database before applying it to the
production database.

## Framework references

- [Odoo 19 upgrade utilities and installation](https://www.odoo.com/documentation/19.0/developer/reference/upgrades/upgrade_utils.html)
- [Odoo 19 module loader and pre-upgrade scripts](https://github.com/odoo/odoo/blob/19.0/odoo/modules/loading.py)
- [Official module rename utilities](https://github.com/odoo/upgrade-util/blob/master/src/util/modules.py)
- [Official field rename utilities](https://github.com/odoo/upgrade-util/blob/master/src/util/fields.py)
- [Odoo 19 action model](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/ir_actions.py)
