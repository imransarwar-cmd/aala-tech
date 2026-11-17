# DVZ Honeywell Project Delivery Costing

Version: **19.0.1.8.0** — Odoo 19

## Configuration

As a Settings administrator, open:

**Project → Configuration → Honeywell Delivery Costing**

The same section is available in **Settings → Honeywell Delivery Costing**.
Choose one option, then click **Save**:

| Option | Behavior |
| --- | --- |
| All Projects | Enable delivery costing for every analytic account, including accounts created later. |
| None | Disable delivery costing synchronization and hide the Delivered Cost smart button. Existing delivery cost lines are retained. |
| Selected Projects | Show a Many2many field of analytic-account names. Select one or more accounts to enable. |

The configuration applies globally, matching the previous account checkbox's
scope. The Many2many selector shows analytic-account names and does not
require a separate `project.project` record. Odoo's existing analytic-account
access rights and company visibility still apply when choosing accounts.

The old editable checkbox is hidden on analytic accounts. Its technical field
name, `dvz_honeywell_delivery_costing`, remains available as a computed,
read-only effective status for the existing delivery hooks and smart button.

Saving a changed configuration synchronizes existing completed deliveries for
newly enabled accounts. Removing an account from the selection or choosing
None does not delete any historical cost lines. The selected list is retained
when switching to All Projects or None so it can be reused later.

## Existing costing behavior retained

**Delivered Cost = Sales Order line Unit Price × actual completed customer
delivery quantity.**

The existing matching and calculation code is unchanged:

1. Match Sales Order lines through their `analytic_distribution`.
2. Retain the optional fallback to existing `analytic_account_id`,
   `account_analytic_id`, or `analytic_id` fields on Sales Orders.
3. Process only completed stock moves with a customer destination and a
   positive delivered quantity.
4. Convert delivered quantity into the Sales Order line's unit of measure,
   and convert the unit price to the company's currency where required.
5. Keep the original 100% allocation rule and one cost line per analytic
   account and stock move; synchronize existing lines instead of duplicating
   them.

Partial deliveries and backorders continue to use their completed stock
moves. Delivery validation continues to trigger synchronization, and the
Delivered Cost smart button continues to refresh the account's delivery
history. Stock valuation and product standard cost are not used. No new
discount, tax, return, or allocation rule has been introduced.

## Upgrade an existing installation

1. Replace the existing `dvz_project_honeywell_delivery_cost` addon directory
   with the folder from this ZIP. Keep the technical module name unchanged.
2. Restart the Odoo service so the updated Python models are loaded.
3. In Apps, find **DVZ Honeywell Project Delivery Costing** and click
   **Upgrade**. Do not uninstall the existing module.
4. Open **Project → Configuration → Honeywell Delivery Costing** and review
   the selected mode and accounts.

The included `19.0.1.8.0` upgrade scripts preserve checked accounts from the
previous version. The pre-upgrade step snapshots them before the old stored
Boolean changes to a computed field. The post-upgrade step restores them as
Selected Projects. Archived enabled accounts and shared accounts are included.
If no account was previously enabled, the initial mode is None.

Migration does not delete, create, or recalculate delivery cost lines. An
upgrade is necessary to create the new fields and load the new configuration
view; restarting alone is insufficient. A fresh installation starts at None.

## Dependencies

- `base_setup`
- `project`
- `dvz_project_purchase_report` (existing custom dependency)
- `sale_stock`
- `stock_account`
- `analytic`

## Verification

Python syntax, XML structure, settings logic, legacy-selection migration, and
preservation of the original costing methods were checked locally. This
workspace does not include an Odoo server or PostgreSQL, so installation and
browser behavior must still be verified in your Odoo 19 environment.

After upgrading, check Save/reopen persistence, the conditional account
selector, smart button visibility, a completed delivery for an enabled
account, and that selecting None retains existing cost lines.

## Framework references

- [Odoo 19 settings implementation](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_config.py)
- [Odoo 19 Project configuration menus](https://github.com/odoo/odoo/blob/19.0/addons/project/views/project_menus.xml)
- [Odoo 19 upgrade scripts](https://www.odoo.com/documentation/19.0/developer/reference/upgrades/upgrade_scripts.html)
