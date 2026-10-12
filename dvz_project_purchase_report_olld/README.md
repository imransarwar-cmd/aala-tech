# Project Reporting - Odoo 19 Community

Project sales, procurement and invoicing reports, grouped by project (analytic account).

## Menus
- **Sales** - Project Sale Orders, Sale Order Lines (agreed price per project).
- **Procurement** - Project Purchase Orders, PO Product Lines.
- **Invoicing** - Vendor Bills, Customer Invoices, Vendor Bill Lines, Customer Invoice Lines.
- On the **analytic account** form: a Project PO smart button.

## How the numbers are built
Everything is allocated by the **analytic distribution** on each line (sale order, purchase
order, bill, invoice), so the project must be set on the line. Amounts are **untaxed**; each
list also shows the project's share converted to **company currency**, so SAR, EUR and USD
documents total correctly.

## Access
No custom groups or record rules. Internal users (`base.group_user`) have **read-only** access
to the report models. They are SQL views, so nobody can create or edit rows; the views also hide
the New / Edit / Delete buttons.

**Security warning:** these SQL views ignore record rules, so every internal user can see every
company's project figures. Do not deploy this variant if that is unacceptable.

## Upgrading
Replace the folder and upgrade (`-u dvz_project_purchase_report`); copying files alone does not
update the database. Needs the Sales app (`sale`) installed.

### Version history
- 19.0.6.0.2 - Removed the Project Profit & Loss dashboard (its query was too heavy for the
  server) together with the Estimated Budget field and the Project Budgets screen. Its SQL view
  is dropped on upgrade.
- 19.0.6.0.1 - Fixed search views invalid on this Odoo 19 build.
- 19.0.6.0.0 - Added the Sales reports and company-currency amounts; fixed the actions opening a
  blank "New" form instead of the list.
