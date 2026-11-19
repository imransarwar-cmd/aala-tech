DVZ Manual Material Reservation
===============================

Odoo 19 Community | dvz_material_manual_reserve | 19.0.3.0.0

This addon provides a saved reservation document, its own product lines,
Confirm button, and a live product report. It is independent of the separate
Reservation View and Automatic SO Reservation addons.

Menus
-----
* Inventory > Operations > Manual Reservations
* Inventory > Operations > Manual Reservation Report

Workflow
--------
1. New: select a Customer, a Project, or both. No Sales Order is required.
2. Select Delivery Operation and Source Location; add products and quantities.
3. Save the Draft. This creates no stock transfer and reserves no inventory.
4. Confirm & Reserve creates one standard outgoing transfer and uses Odoo's
   native reservation methods. It reserves available stock only.
5. Review Requested Qty, Reserved Qty, To Reserve, and optional Delivered Qty.
   Use Transfers to open the native operation, including its lots and serials.
6. Check Availability retries a short reservation after stock becomes available.
7. Unreserve releases pending, unpicked stock through Odoo. Cancel also cancels
   its pending transfer demand. Neither action deletes the saved request.

Confirming this document does not confirm a Sales Order or validate a delivery.
Products with lots/serials use Odoo's normal stock removal and reservation rules.

Report
------
The Product Report button opens one request's lines. The report menu shows
confirmed requests across the user's active companies. Search or group by
request, customer, project, SO reference or product. Optional columns use the
standard Odoo column selector; normal list export is available with export access.

* Requested Qty: the original quantity on the saved request.
* Reserved Qty: currently reserved pending outbound stock, excluding done/cancelled moves.
* Delivered Qty: completed outbound quantity less linked completed customer returns.
* To Reserve: max(Requested - Delivered - Reserved, 0); zero on cancelled requests.

Quantities use the product's stock unit. Backorder movements retain the request
line reference. There is no grand total across different units or products.
Customer returns update net Delivered Qty; they do not automatically create a
replacement outbound demand. Create a new request if replacement stock is needed.

Native stock behaviour
----------------------
Business code creates stock.picking and stock.move demand records, then calls
native confirmation/assignment/unreserve/cancel methods. It never creates,
writes or deletes stock.move.line or stock.quant records directly.

Requested materials are frozen after confirmation. Further picking/packing and
delivery validation happen in Odoo's native Transfer form. An unreserve is not
a permanent hold cancellation: the pending demand remains, and native scheduling
or another Check Availability can reserve it again. Cancel ends that demand.
Picked materials must be reviewed on the transfer before unreserving. Requests
with completed movements cannot be cancelled from the request form; manage their
remaining backorders through Inventory.

Optional SO reference
---------------------
A draft/sent quotation can be recorded as an informational SO Reference. It
remains unconfirmed. A confirmed SO must use its existing delivery rather than
create a second demand here. Manual transfers contribute their own stock demand.
Before later confirming a referenced quotation, cancel the unused manual hold or
reconcile the intended fulfilment; these separate modules do not automatically
convert a manual transfer into that SO's delivery.

Install or upgrade
------------------
1. Put the dvz_material_manual_reserve folder in your configured addons path.
   Replace this module's files with the supplied version; retain the separate
   View and Auto addons as they are.
2. Stop the Odoo processes using the target database during installation/upgrade.
3. Restart Odoo, update the Apps list, clear the Apps search filter, and locate
   DVZ Manual Material Reservation. Install it, or Upgrade if already installed.
4. Users need their normal Inventory access and access to any selected project
   or quotation. Company restrictions and stock permissions remain in effect.

This version supersedes the old transient manual wizard. Existing transfers and
the dvz_manual_project_id/dvz_manual_so_id values are preserved during upgrade.
Old transfers are not silently converted into new request documents. New requests
appear in the new report; earlier transfers remain in Inventory and the separate
reservation view. The View and Auto modules are neither bundled nor modified.

Database lock timeouts or pre-existing dangling foreign-key links require their
own database maintenance; this addon does not delete or repair unrelated data.

License: LGPL-3.0
