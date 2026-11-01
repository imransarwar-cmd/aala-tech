# SO Project Naming — Odoo 19

Version: 19.0.1.0.0  
Technical module: `dvz_sale_project_naming`

## Requested workflow

A sales order already uses Odoo's automatic project creation. This add-on changes
its generated project's name, not the sales order sequence and not the creation policy.

Example inputs:

| Input | Example |
|---|---|
| Existing SO number | S00642 |
| Assigned salesperson's user abbreviation | AIB |
| Division / Department code | EM |
| Project Reference | 4128 |
| Optional Project Suffix | VO |

Project code: `AIB-EM-4128-VO`  
Default project name: `S00642 || AIB-EM-4128-VO`

Turn off **Include SO Number in Project Name** before confirming to use only
`AIB-EM-4128-VO` as the project name. Leaving the suffix blank gives
`S00642 || AIB-EM-4128`.

`4128` is an entered business reference, not an automatically generated sequence.
`VO` is optional text. The add-on does not assume what VO stands for or automatically
classify a variation order. EM's full division name must be entered by your administrator.
The new division master is independent of the HR Departments model; HR is not required.
The existing Customer field remains unchanged.
Business reference uniqueness is not enforced; use distinct references as needed. The
default inclusion of the SO number distinguishes different orders with the same code.

## Installation

1. Back up the database and filestore. Install first on a staging copy.
2. Extract the ZIP; copy the entire `dvz_sale_project_naming` directory into a directory
   already included in the Odoo server's `addons_path`.
3. Restart Odoo. Enable developer mode, then use Apps > Update Apps List.
4. Remove the default Apps filter, search **SO Project Naming**, and install.
5. This is a new, separate add-on. Do not replace/uninstall the SO–Invoice Linker or
   the Internal Transfer module supplied earlier.

Dependencies: `sale_management` and `sale_project`. These provide the native sales/project
flow. No external Python package is required to run the add-on.

## One-time setup

### Salesperson abbreviation

As a Settings Administrator, open Settings > Users & Companies > Users.
Open the relevant internal salesperson and go to **Preferences**.
Set **Salesperson Abbreviation** to `AIB`, then save.

Set a code for each salesperson used in this naming workflow. The abbreviation is
read from the **Salesperson assigned to the SO**, not from the logged-in user.
It is not guessed from initials, email address, or customer name.

### Divisions / Departments

As a Sales Administrator, open Sales > Configuration > Divisions / Departments.
Create a record with its full department name, **Code = EM**, and the correct company.
Codes must be unique within a company. Only active divisions from the sales order's
company are offered by the SO dropdown. Archive obsolete divisions instead of deleting
records in use.

## Per-order use

Open the quotation and go to **Other Info > Sales**. The new **Division / Department**
field is immediately after the existing Salesperson field.

Select the division, enter **Project Reference = 4128**, and enter **Project Suffix = VO**
where appropriate. Review **Project Code** and **Generated Project Name**, then confirm.

The native creation process creates the project and this add-on applies the chosen name.
The original SO number, e.g. `S00642`, is not changed. The standard project links and
smart buttons are left intact; no custom smart buttons are added.

A naming snapshot is saved when the order is confirmed. Later changes to a salesperson's
abbreviation or a division's code do not rename this order's existing project or change
its saved naming code. The naming inputs are locked once that snapshot exists, including
when a confirmed order is cancelled and reset to draft. Other SO behavior remains native.
For a new project reference, duplicate the order and enter a new reference before confirming.
A duplicate does not inherit the reference, suffix, or naming snapshot.

The project name itself remains editable by users who already have project write rights.
Manually editing a project name does not rewrite the saved SO naming snapshot.

## Existing automatic-creation configuration

Keep ONE existing project-creation mechanism. This add-on is a naming extension, not a
second automatic-creation rule.

### Standard product configuration

Supported native service product modes are **Project** and **Project & Task**
(`project_only` and `task_in_project`). Existing templates remain in use; the generated
project gets the exact selected format without an appended product/template title.
Template tasks and the existing project manager assignment are not replaced by this add-on.

A product configured for **Task in an existing project** must keep the existing project
name. This add-on does not rename shared/global projects, create an extra project for
ordinary products, or force multiple native projects into a single project.

If native configuration generates multiple projects for one SO, it can give all of those
new projects the same requested title. Configure one native project per SO when a single
project is required; this add-on does not merge projects.

### Studio / automated actions / custom code

A directly created project is recognized only when it includes a standard relationship:
`sale_line_id` (an actual SO line) or `reinvoiced_sale_order_id` (the SO).
The order must be confirmed. Context defaults for these fields are supported as well.

An automation that creates an unlinked project with only `name = order.name` is NOT enough
for reliable matching. Before rollout, its administrator must set the native order link
in that existing action, or use the standard product-based creation workflow instead.
Do not add a second create action. Do not attempt matching by text or project name.
An action that links the SO only in a later write, or uses an unknown Studio custom
relation instead of these native fields, requires review of that action before use.
Projects intentionally referencing different SOs through both native fields are not
automatically named by the direct-create hook, because the owner is ambiguous.

The exact existing automation and other custom modules on your server were not supplied
or inspected. Compatibility with those actions must therefore be checked on staging.

## Scope and protections

- With division, reference, and suffix all blank, native behavior is unchanged.
- Once any naming input is entered, a division, reference, and assigned salesperson
  abbreviation are required at confirmation. The suffix is optional.
- Codes are normalized to uppercase. Abbreviation/division/suffix: 1–16 English letters
  or digits; reference: 1–40 letters/digits with single `-`, `.`, `_`, or `/` separators.
- No historical projects are renamed at installation. No backfill is run.
- No SO number, invoice link, invoice amount, tax, payment, or accounting entry is rewritten.
- No analytic account is renamed by this add-on; native analytic creation is left alone.
- No new invoice/SO/project smart buttons are inserted.
- Existing correct project counts/links remain the native module's responsibility.
- Division access is company-restricted. Internal users can read divisions; Sales/Settings
  administrators can maintain them. No portal/public division access is granted.
- Frozen references are not unlocked by resetting an order to draft.

## Staging acceptance checks

Use a new test quotation, not an existing live sales order.

1. Set AIB on the assigned salesperson, create the appropriate EM division, and enter
   4128 and VO on a quotation that uses the existing native project-generating product.
2. Confirm. Verify the project name is `<actual SO number> || AIB-EM-4128-VO` and its
   native SO relation points to the same order. The SO number must not be rewritten.
3. Verify there is only the number of projects your existing native configuration expects.
4. Repeat with a project template, without a suffix, and with Include SO Number switched off.
5. Verify a shared/global project used for tasks is not renamed and ordinary products do not
   acquire projects merely because naming fields were completed.
6. Verify missing input raises a clear message and another company's division cannot be used.
7. Verify later abbreviation/code changes do not rename earlier confirmed projects.
8. Check a normal Sales user, a Project user, and your actual automated action's execution user.
9. Check both installed customizations (SO–Invoice Linker and Internal Transfer) remain unaffected.

## Tests and verification status

Standalone checks are in `qa/test_standalone.py`. They test pure naming helpers, syntax,
XML structure, manifest paths, ACL intent, and selected code-structure safeguards only:

```bash
python /path/to/dvz_sale_project_naming/qa/test_standalone.py
```

The QA script uses `lxml`, which is already part of the usual Odoo Python environment.
It is not imported by the module's runtime.

Odoo integration tests are included under `tests/`. On a disposable Odoo 19 test database,
using your real executable/config paths:

```bash
odoo-bin -c /path/to/odoo.conf -d NAMING_TEST_DB \
  -i dvz_sale_project_naming --test-enable \
  --test-tags /dvz_sale_project_naming --stop-after-init
```

Use `-u` instead of `-i` when the add-on is already installed on that test database.
Never point this test command at production.

There is no running Odoo/PostgreSQL instance in the build environment. Live installation,
ORM behavior, inherited-view validation, record rules, template copy behavior, and browser
behavior have NOT been executed here. The integration tests are supplied for your staging
administrator, not claimed as passed. See `QA_REPORT.md` for standalone results.

## Technical structure

| Model | Fields / extension |
|---|---|
| `dvz.sale.division` | New division master: name, code, company, active, sequence |
| `res.users` | `dvz_sales_abbreviation` |
| `sale.order` | Division, reference, suffix, format option, code/name preview, confirmation snapshot |
| `sale.order.line` | Inherits native project preparation and creation hooks |
| `project.project` | Naming metadata and native-linked direct-create naming hook |

No SQL data patch, scheduled job, HTTP route, or direct database write is used.

## Official compatibility references reviewed

The implementation was checked against the Odoo 19.0 branch and documentation:

- https://raw.githubusercontent.com/odoo/odoo/19.0/addons/sale_project/models/sale_order_line.py
- https://raw.githubusercontent.com/odoo/odoo/19.0/addons/sale_project/models/sale_order.py
- https://raw.githubusercontent.com/odoo/odoo/19.0/addons/sale_project/models/project_project.py
- https://raw.githubusercontent.com/odoo/odoo/19.0/addons/sale/views/sale_order_views.xml
- https://raw.githubusercontent.com/odoo/odoo/19.0/odoo/addons/base/views/res_users_views.xml
- https://raw.githubusercontent.com/odoo/odoo/19.0/addons/project/views/project_project_views.xml
- https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html
- https://www.odoo.com/documentation/19.0/applications/services/project/project_management/project_templates.html

These are compatibility references, not a claim that every customized Odoo 19 build has
identical views or automation overrides.
