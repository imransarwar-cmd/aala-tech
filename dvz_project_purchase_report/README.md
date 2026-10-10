# Project Reporting v6 - Odoo 19 Community

Project sales, procurement, invoicing, budget and profit & loss reports, under one app.

## Menus
- **Project Profit & Loss** - one row per project: agreed price, budget, committed cost,
  billed cost, invoiced revenue, expected / actual / planned profit and margin. List, pivot,
  graph and a one-page form per project with buttons to its sale orders, POs, bills, invoices.
- **Sales** - Project Sale Orders, Sale Order Lines (agreed price per project).
- **Procurement** - Project Purchase Orders, PO Product Lines.
- **Invoicing** - Vendor Bills, Customer Invoices, Vendor Bill Lines, Customer Invoice Lines.
- **Configuration > Project Budgets** (Accountants) - type the Estimated Budget per project.

## How the numbers are built
Everything is allocated by the **analytic distribution** on each line (sale order, purchase
order, bill, invoice), so the project must be set on the line. All figures are **untaxed and in
company currency** (so SAR, EUR and USD documents add up correctly).

| Figure | Source |
|---|---|
| Agreed price | confirmed sale orders |
| Estimated budget | typed on the analytic account (Project Budget) |
| Committed cost | confirmed purchase orders |
| Billed cost | posted vendor bills (credit notes subtract) |
| Invoiced revenue | posted customer invoices (credit notes subtract) |
| Expected profit | agreed - committed |
| Actual profit to date | invoiced - billed |
| Planned profit | agreed - budget |

Labour, stock consumption, overhead and other costs that are not on a vendor bill are not
included. Test on staging before production.

## Access
No custom groups or record rules. Internal users (`base.group_user`) have **read-only** access to
the report models, except `dvz.project.dashboard` which has read + write + create access as
requested. They are all SQL views, so no real rows can be created or edited either way - the
views also hide the New / Edit / Delete buttons. The Configuration menu
is for Accountants (`account.group_account_user`).

**Security warning:** these SQL views ignore record rules, so every internal user can see
every company's project figures. Do not deploy this variant if that is unacceptable.

## Upgrading
Replace the folder and upgrade (`-u dvz_project_purchase_report`); files alone do not update
the database. The 19.0.6.0.0 migration removes old view-order records that made every menu
open a blank "New" form first. Needs the Sales app (`sale`) installed.
