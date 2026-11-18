DVZ Sales Stock & Purchase Report — Odoo 19 Community
===================================================

Technical name: ``dvz_sale_supply_report``
Version: ``19.0.1.2.0``

Purpose
-------

An installable reporting addon showing one row for every sales-order product
line, with a formatted Excel download. Repeated products on different lines
remain separate. It can be installed alongside the separate
``dvz_sale_order_quantity_summary`` and ``dvz_material_reservation`` addons:
it reads the native sales lines and stock moves used by those workflows and
does not depend on their custom model names. Compatibility with a particular
custom installation still requires a test-database installation.

Where to find it
---------------

* Sales > Supply Reports > Sales Supply Report.
* Sales > Supply Reports > Export Sales Supply to Excel.
* On a sales order: the **Stock / Purchase Report** and **Supply Excel** buttons.
* In the product report: click **Export Excel** and select one or more SOs.
  Selecting report rows first prefills their SOs and includes all those orders'
  product lines.

The list and form are read-only. They show SO name, customer, order date,
product code, product, full line description, UoM, ordered quantity, delivered
quantity, pending quantity, source split, total sourced quantity, current
reservations, source references and source evidence. Warehouse, salesperson,
company, unit price and untaxed subtotal are available as additional columns.

Search by SO/customer/product, and group by SO, customer, product, warehouse,
salesperson, month or company. The report opens on confirmed orders; quotation
and cancelled-order filters are available. Opening it from an SO shows that
order's product lines, even when it is still a quotation.

Your 8 = 6 + 2 example
---------------------

For a product with 8 units required and a documented source split of 6 from
existing stock and 2 from a purchase:

=========================  ====================  ==================
Column                     Before delivery       After full delivery
=========================  ====================  ==================
Order Qty                  8                     8
Delivered Qty              0                     8
Pending Qty                8                     0
From Stock Qty             6                     6
From Purchase Qty          2                     2
Total Source Qty           8                     8
Source Unassigned Qty      0                     0
Used from Stock Qty        0                     6
Used from Purchase Qty     0                     2
Delivered Source Unknown   0                     0
=========================  ====================  ==================

The actual delivered split is recorded after delivery, or obtained from an
unambiguous purchase-linked movement chain. A supply plan does not count as
a delivery. A stock shortage does not count as a purchase order.

What is calculated automatically
--------------------------------

* Ordered quantity comes from the sales line.
* Delivered quantity is Odoo's own net-delivery figure, including the returns
  Odoo counts for that sales line. Internal pick/pack/ship steps are not added
  together as extra deliveries.
* Pending Qty = max(Order Qty - Delivered Qty, 0).
* Overdelivered Qty = max(Delivered Qty - Order Qty, 0).
* Reserved Now is open warehouse stock reserved against that sales line,
  capped at its pending demand. It is separate from delivered quantities.
* Free Stock Now is the present unreserved balance in the relevant warehouse,
  expressed in the line's UoM. It is reference information and is never
  automatically assigned to every order or totalled across product lines.
* A purchase source can be identified automatically where each customer
  delivery has a sufficient, exclusive, single-parent chain to a confirmed
  purchase line. The report counts the delivery demand/quantity, not the
  entire purchase order. Completed parents must precede the delivery and
  connect through the same physical locations.
* Total Source Qty = From Stock Qty + From Purchase Qty.
* Source Unassigned Qty = max(Order Qty - Total Source Qty, 0).
* Delivered Source Unknown = max(Delivered Qty - Used from Stock Qty -
  Used from Purchase Qty, 0).

Source Unassigned means the source is not established in this report. It can
include goods already reserved or delivered. It is not an instruction to buy
that quantity, and it is not the same as a physical stock shortage.

Date filters help locate SOs by order date in the SO selector. Explicitly
selected orders are always included in full. Stock and delivery numbers are
current when the report is opened/exported; this is not an inventory report
as of the filter's end date.

Recording a mixed stock/purchase split
-------------------------------------

Current stock does not prove where an old delivery came from. Generic stock
replenishments, merged receipts, shared supply moves, and old transactions
often do not contain an exact sales-line source split. Such sources remain
unverified; the addon does not invent an 8-stock or 6-stock/2-purchase history.

A Sales Administrator/Manager can record the known split:

1. Open the sales product line in the report and click **Set Source Split**
   (or the sliders icon beside the row).
2. For 8 required, enter 6 in **Supply from Existing Stock** and 2 in
   **Supply from Purchase**. These supply figures include any quantities
   already delivered.
3. Enter the net quantities actually delivered from each source. Before any
   delivery, leave both delivered-source fields at zero.
4. Enter a short evidence note. Users with Purchase access may also select
   supporting confirmed PO lines for the same product/company.
5. Click **Save Source Split**.

Supporting PO references are evidence links, not exclusive reservations of a
PO's quantity. A recorded purchase-supply plan without a PO link is displayed
as a recorded declaration; no PO is created or fabricated.

The report records who entered the split and when. Changes and resets are
logged as internal notes on the sales order. Negative source values, supply
above the greater of ordered/delivered quantities, usage above delivered
quantity, usage above its source plan and empty evidence notes are rejected.

If the delivered quantity later changes, the current delivered-source figures
become unverified until the manager reviews the split. The original recorded
values remain available in the editing wizard. Product/UoM changes invalidate
the entire old source split. Order quantity changes and cancelled supporting
POs show review messages. **Reset to Automatic** clears the manual source
entry and returns to the available Odoo movement evidence.

The addon does not confirm orders, make purchases, reserve/unreserve products,
change stock moves, or alter sale quantities. Those actions stay in the normal
Sales, Inventory, Purchase and existing material-reservation workflows.

Excel export
------------

**Sales Orders are mandatory.** Select one or more SOs, then generate the
report. Every product line belonging to those orders is included, including
repeated products. There is no Products selector and no separate selected-line
export mode. Sections, notes and down-payment accounting lines are excluded.

Optional date, customer, company and status filters help find orders in the
Sales Orders selector. They do not remove an order that has already been
explicitly selected. Dates include the whole end date in the user's timezone.
The selector initially lists confirmed orders; quotations/cancelled orders
can be included when required.

Opening the wizard from an SO prefills that order. Opening it from selected
product rows prefills their parent SOs and includes every sibling product
line. Without an SO, export is blocked in both the screen and server logic.

**View Product Details** opens the selected SOs' full product report in Odoo.

Click **Generate Excel**, then click the generated Excel filename.
The file contains one **Sales Report** worksheet with exactly five columns:

1. SO
2. Product Name
3. Order Qty
4. Delivered Qty
5. Used from Stock

Every product line is retained separately, including repeated products.
There are no extra worksheets, summary totals, hidden data columns, prices,
or customer/date columns. The header is frozen and filters are enabled.
Quantities are numeric, and names are exported literally as safe text.

Used from Stock is the actual net delivered stock-source quantity, not the
planned stock allocation or current warehouse availability. When its source
is unresolved, the compact Excel cell shows **0** (no verified stock quantity) while the Odoo detailed view preserves the source warning. Services show **0**. All
quantities follow the sales line unit; quantities across rows are not summed.

The export limit is 10,000 product lines per file to bound worker memory use.
For larger reports, export smaller groups of SOs. This is a quantity
and sourcing report, not a purchase-cost or inventory-valuation report.

Installation
------------

Requirements: Odoo 19 Community, Sales, Sales/Inventory integration, Purchase/
Inventory integration, and Python ``xlsxwriter``. The manifest installs the
Community dependencies ``sale_management``, ``sale_stock``, ``purchase_stock``.
The ordinary Odoo 19 requirements include xlsxwriter; no OCA report engine or
Enterprise addon is needed.

1. Extract the archive. Copy the inner ``dvz_sale_supply_report`` directory
   into the custom addons directory listed in your Odoo ``addons_path``.
   The manifest must be directly inside that directory; avoid double nesting.
2. Restart the Odoo service that runs that addons path.
3. Enable developer mode, open Apps, and choose **Update Apps List**.
4. Remove the default **Apps** search filter if the addon is not visible
   (this is an extension, not a standalone application).
5. Search **DVZ Sales Stock & Purchase Report** and click **Install**.
6. Refresh the Sales app and open **Supply Reports**.

Upgrading an earlier version
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Replace the existing ``dvz_sale_supply_report`` folder with this version,
restart Odoo, and choose **Upgrade** on the existing addon in Apps. Then
refresh the browser. The technical addon name is unchanged. No uninstall is
required. This release simplifies the Excel report to the five requested
columns. Sales Orders remain mandatory, and every product line belonging to
the selected orders is included.

Use a test database for the initial installation and the included Odoo tests.
If xlsxwriter is missing, install it in the same Python environment used by
the Odoo service, then restart Odoo.

Example CLI installation on a test database::

    /path/to/odoo-bin -c /path/to/odoo.conf -d YOUR_TEST_DATABASE \
        -i dvz_sale_supply_report --stop-after-init

For an update, replace ``-i`` with ``-u``. Use your actual executable, config,
addons path and database; no production connection details are embedded.

Access
------

The report reads native ``sale.order.line`` records and preserves their
salesperson/company rules. Exports use the requesting user's normal access;
there are no sudo report searches. Source-entry changes require Sales
Administrator/Manager access, including direct RPC writes and context-default
creation. Internal sourcing fields are restricted to internal users so portal
customers cannot request source notes or PO links through RPC. PO details
still require the relevant Purchase access. Missing stock/PO access is shown
in Source Basis instead of using elevated privileges.

Validation and technical limits
-------------------------------

Performed in the build workspace: Python syntax checks, XML parsing and
reference checks, 20 framework-independent quantity tests, and real in-memory
XLSX generation/structure and formula-injection checks. APIs were checked
against official Odoo 19.0 source.

Odoo installation, ORM constraints, browser rendering and full integration
tests have not been executed here because the workspace does not have Odoo
or PostgreSQL. The included tests cover orders, reservations, returns, source
entry, procurement-chain edge cases, permissions and export behavior for
execution on an Odoo test database::

    /path/to/odoo-bin -c /path/to/odoo.conf -d YOUR_TEST_DATABASE \
        -i dvz_sale_supply_report --test-enable \
        --test-tags /dvz_sale_supply_report --stop-after-init

The pure quantity checks can run without Odoo::

    python3 tests/test_quantity_math_standalone.py

Source computations are current, non-stored report fields. Grouped list
headers do not calculate full supply totals. The compact Excel export also keeps product lines
separate and does not add mixed-unit totals. The report's own view/action IDs
and field prefixes avoid replacing the earlier quantity-summary views.

Official compatibility references
---------------------------------

* https://github.com/odoo/odoo/blob/19.0/addons/sale_stock/models/sale_order_line.py
* https://github.com/odoo/odoo/blob/19.0/addons/stock/models/stock_move.py
* https://github.com/odoo/odoo/blob/19.0/addons/purchase_stock/models/stock_move.py
* https://github.com/odoo/odoo/blob/19.0/addons/web/controllers/export.py
* https://www.odoo.com/documentation/19.0/developer/reference/user_interface/view_architectures.html

Version 19.0.1.3.0: Sales Supply Report list shows exactly the same five visible
columns as the Excel export: SO, Product Name, Order Qty, Delivered Qty,
and Used from Stock. Additional record information is retained in the
line form view for drill-down; the existing SO selection wizard is unchanged.
