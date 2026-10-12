# Project Amount Smart Buttons - Odoo 19 Community

Two smart buttons on the **analytic account** form. Each opens the documents linked to that
project and shows **only the project's own share** of every amount (not the full document total).

| Button | Opens | Shows |
|---|---|---|
| **Project PO Amount** | the project's purchase orders | Project Amount (Untaxed) per PO |
| **Project Bill Amount** | the project's vendor bills and credit notes | Project Amount per bill, in bill currency and in company currency; the button itself shows the total of the **posted** bills (credit notes subtract) |

How the share is worked out: each PO / bill line carries an analytic distribution
(e.g. Project A 60%, Project B 40%). The project amount is the line's untaxed amount times
the project's percentage, added up per document. Draft bills are listed (status shown) but are
not in the button total until posted.

## What this module does NOT do
No menus, no report tables, no database views, no stored data. Amounts are computed on the fly,
only for the documents on screen, so it adds essentially no load to the database.

## Access
Nothing to configure. It adds no groups, record rules or access rows; users see only what
Odoo already lets them see.

## Upgrading from the old "Project Reporting" app (19.0.6.x)
Replace the folder and upgrade (`-u dvz_project_purchase_report`). The upgrade removes the old
menus, report models and their SQL views. Nothing in sales, purchase or accounting is changed.

### Version history
- 19.0.7.0.0 - Added the Project Bill Amount button. Removed the Project Reporting app (menus,
  sales/procurement/invoicing reports, dashboard) and all SQL views.
- 19.0.6.x - Report app versions (removed).
