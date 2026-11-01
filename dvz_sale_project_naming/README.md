# SO Project Naming — Project Information, Division Menu and Chatter

**Technical module:** `dvz_sale_project_naming`  
**Version:** `19.0.1.1.0`  
**Target:** self-hosted Odoo 19, with Sales and Sales/Project integration installed.

This is an update to the existing naming module, not a second naming add-on.
Upgrade the installed module; do not uninstall it.

## Changes in this update

### 1. Project Information on the quotation / sales-order form

The existing division field is moved from Other Info to a separate **Project Information**
section below the standard customer/order header and above the order-line notebook.
The section reuses the custom fields already present on the main form.

| Left column, in order | Right column, in order |
| --- | --- |
| Division / Department | Estimation Engineer |
| System | Remarks |
| Project | Client/Product Logo |
| Brand | |
| Area | |
| Priority | |

**Division / Department appears before System.** It remains the same field,
`dvz_division_id`, pointing to the same `dvz.sale.division` master records. There is no
new division table or duplicate set of division values.

The screenshot's custom Project description is distinct from the automatically
created `project.project` record and its generated name. This update does not
replace that description with the generated project code.

The customer, dates, pricelist, payment terms, order lines, totals, existing smart
buttons and standard SO chatter are not intentionally changed.

### 2. Separate Project Naming section

Under **Other Info → Project Naming**, the form contains:

- Salesperson Abbreviation, read from the SO's assigned salesperson;
- Project Reference;
- optional Project Suffix;
- Include SO Number in Project Name;
- Project Code and Generated Project Name previews.

The division selection is not duplicated in this section. Existing naming rules,
confirmation validations and snapshots are unchanged. For example:

```text
SO:            S00642
Salesperson:   AIB
Division:      EM
Reference:     4128
Suffix:        VO
Project code:  AIB-EM-4128-VO
Project name:  S00642 || AIB-EM-4128-VO
```

`4128` is still entered manually. Selecting a division opts the order into the
existing naming validation: a salesperson abbreviation and project reference are
needed before confirmation. Clearing all naming inputs leaves the original native
workflow available. Naming inputs already frozen on confirmed orders remain
read-only; this UI update does not unfreeze them or rename historical projects.

### 3. Divisions / Departments menu under Orders

The same division list is available in both places:

- **Sales → Orders → Divisions / Departments** for Sales users and Settings administrators;
- **Sales → Configuration → Divisions / Departments** for Sales Managers and Settings administrators.

Both menus use the existing action and master model. This is a shared list, not
separate configuration for quotations and orders. Selecting a division on an SO
uses this same list. The existing Division search, list column and **Group By →
Division / Department** option remain available for quotations and orders.

A Project Manager or Project HOD role does not by itself give Sales Manager rights.
This update does not change the separate project-security module or its groups.

### 4. Chatter on each division record

Open a division from either menu. Its form now includes standard Odoo chatter,
implemented with `mail.thread`, `mail.activity.mixin` and a single `<chatter/>`.
It supports messages, internal notes, followers, attachments and activities,
subject to normal Odoo permissions. The list also has an optional Activities column.

The following changes are tracked from this upgrade onward:

- Division / Department Name;
- Code;
- Company;
- Active / Archived status.

Existing records are preserved. Earlier changes are not reconstructed as historical
messages. There is no second chatter inserted inside the SO form's Project Information
section; the division and SO are separate discussions.

Internal users who can read a division can post to its chatter without obtaining
permission to change its master fields (`_mail_post_access = 'read'`). Sales Managers
and Settings administrators retain master create/write/delete rights. Company rules
remain unchanged. Activity operations and attachment/follower operations also obey
Odoo's native mail permissions; this module does not use sudo to bypass them.

Outgoing email delivery requires the server's normal mail configuration. Messages
can notify followers or selected recipients. Use internal notes for internal discussion;
do not add external followers or recipients to confidential division discussions.
No public/portal model access or division email alias is added.

## Installation / upgrade

1. Back up the database, filestore and installed custom-addons folder. Test on a
   staging copy first, with outgoing email disabled or redirected.
2. Extract `dvz_sale_project_naming_19.0.1.1.0.zip`. Replace the existing
   `dvz_sale_project_naming` directory in the configured custom-addons location.
   Keep one copy on the effective addons path.
3. Restart the Odoo service so it loads the updated Python code.
4. Enable developer mode. Open Apps, update the Apps List if needed, and find
   **SO Project Naming - Salesperson and Division**. Remove the default Apps filter
   if the technical add-on is hidden.
5. Choose **Upgrade** on the installed module. A service restart alone does not
   apply the changed views, menu record or mail-related model schema.
6. Refresh the browser and test a quotation, a confirmed order, and a division.

Do not uninstall the naming module. Do not replace the Project Assignment Security,
SO–Invoice Linker or Internal Transfer add-ons with this package. They are separate
modules and are not included here.

For an administrator using the command line, the equivalent upgrade is:

```bash
/path/to/odoo-bin -c /path/to/odoo.conf -d DATABASE_NAME \
  -u dvz_sale_project_naming --stop-after-init
```

Replace the paths and database name with actual values. Run with the Odoo service
account and normal addons paths during a controlled maintenance window, with normal
workers stopped for the upgrade, then restart the service.

## Customized-field matching and limitations

The screenshot does not expose the technical names of your Studio/custom fields.
Instead of inventing field names or modifying your Studio view records, this update
processes the combined SO form architecture after inherited views have been combined
and before Odoo's per-user access-right processing.

The helper in `layout.py` recognizes the existing main-form fields from exact
normalized English labels, metadata labels, or standard-looking technical names.
Recognized roles are System, Project, Brand, Area, Priority, Estimation Engineer,
Remarks and Client/Product Logo. It moves the existing XML nodes, including their
widgets/options/domain/context and field-level modifiers. Ancestor security and
visibility scopes are retained. Existing single-field image wrappers and their
explicit labels are moved together.

It does not create replacement custom fields or write their data. It does not move
fields from order-line subviews, notebook tabs, the native project relationship,
or permanently hidden helper fields. It does not rewrite stored Studio views or
record rules.

**Ambiguous labels, multiple matching widgets, unsupported wrappers and unrecognized
custom fields are deliberately left in place.** A warning is written to the Odoo log
for skipped ambiguous/unsupported roles. The section is still added and Division is
still first. Non-English-only opaque custom labels may require an explicit mapping.
Your actual database's combined view XML was not supplied, so final positioning must
be checked on staging. The synthetic screenshot-equivalent layout is covered by the
offline tests; it is not a substitute for a browser test against your database.

For troubleshooting, search the server log for `DVZ Project Information`. Check the
field's Technical Name, type and label in developer mode and the combined SO form
architecture. Do not add another field just to work around a layout mismatch.

## Staging acceptance checks

- Confirm all eight existing custom values are unchanged and displayed once inside
  Project Information. Check Division immediately before System, tag widgets, logo
  size, required conditions and read-only conditions.
- Check the grouping on quotations and confirmed sales orders, and on a normal Sales
  user as well as an administrator. Check any customized mobile layout separately.
- Confirm Other Info has the separate Project Naming section and no second Division field.
- Open both Division menus: they should show the same records within permitted companies.
- Post an internal note, schedule an activity as an authorized manager, and check the
  division's chatter. Change a test division's name/code and confirm the tracking entries.
- Verify a normal Sales user can discuss a readable division but cannot edit its name/code.
- Confirm a test order through the existing project-creation workflow and verify the
  expected generated name and original native project links.
- Recheck project/task visibility with the separately installed security add-on.

## Validation status

**Executed here:** 79 standalone tests, Python AST and bytecode compilation, XML
well-formedness checks, unchanged-business-logic comparison against version 19.0.1.0.0,
and ZIP integrity verification. The offline layout tests exercise representative XML
only, not Odoo's full view compiler or a browser.

**Not executed here:** live Odoo installation/upgrade, ORM tests, real email delivery,
actual Studio view rendering and browser/access-right behavior in your database.
No Odoo runtime or PostgreSQL server is available in this build environment.

The package contains 28 Odoo integration tests for a disposable staging database:
19 original project-naming tests and 9 new menu/chatter/view tests. They have not been
run here. Use normal Odoo `--test-enable` / `--test-tags /dvz_sale_project_naming`
options with an isolated database and review any interaction with other add-ons.

See `QA_REPORT.md` for the exact offline checks and `qa/` for the executable tests.

## Official implementation references

- Odoo 19 mixins and chatter: https://www.odoo.com/documentation/19.0/developer/reference/backend/mixins.html
- Odoo 19 mail-thread access behavior: https://github.com/odoo/odoo/blob/19.0/addons/mail/models/mail_thread.py
- Odoo 19 Sales menus: https://github.com/odoo/odoo/blob/19.0/addons/sale/views/sale_menus.xml
- Odoo 19 Sales views: https://github.com/odoo/odoo/blob/19.0/addons/sale/views/sale_order_views.xml
- Odoo 19 view combination/postprocessing: https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/ir_ui_view.py
