DVZ Material Reservation View
=============================

Odoo 19 Community | Technical name: dvz_material_reservation_view

Menu: Inventory > Material Reservations > Reservations

Screens
-------
* List: transfer, customer/delivery address, product, reserved quantity,
  unit, source location and status.
* Form: the same details, plus destination, source document, scheduled date
  and lot/serial number when applicable.
* Search by product, customer, transfer or source document.
* Group by product, transfer or source location.

Existing stock reservations appear automatically. Each row represents one
reserved stock operation line; lots or locations can split one product into
several rows. The unit is always visible. No mixed-unit total is displayed.

Install
-------
1. Extract dvz_material_reservation_view into your configured addons folder.
   On your Mac, that is normally /Users/apple/Documents/odoo-19.0/aala-tech.
2. Restart Odoo.
3. In developer mode, open Apps > Update Apps List.
4. Clear the Apps search filter, search for "DVZ Material Reservation View"
   and install it.
5. Open Inventory > Material Reservations > Reservations.

Only the standard Inventory addon (stock) is required. Users need their normal
Inventory access. The older dvz_material_reservation addon is not a dependency.

What is shown
-------------
Positive-quantity stock operation lines for tracked products, from internal
locations, whose stock movement is waiting, confirmed, partially available
or assigned. Done, cancelled, draft and zero-quantity lines are excluded.
Picked but unfinished reservations remain visible. Completed or fully
unreserved lines disappear after refreshing the view.

The customer column shows the transfer's customer/delivery address. It may be
empty for an internal transfer. Source Document shows the existing operation
origin, often the sales order reference. It does not infer a project name.

The list and form are read-only. Click the Transfer link to use Odoo's normal
reserve/unreserve workflow. Existing stock permissions and company rules
still apply; this addon does not remove users' editing rights on other screens.

This addon contains menus, actions and views only. It does not add stock tables,
change reservation quantities, create projects or repair database constraints.
If the earlier stock_reference_move_rel_move_id_fkey error persists, resolve
the confirmed orphan-link problem separately before retrying installation.

Quick check
-----------
Reserve a tracked product on an internal-source transfer using Odoo's normal
workflow. The reserved quantity and source location should appear here.
Open the row to check the detail form. Unreserve or complete the transfer,
then refresh this screen; its released/completed lines should disappear.

License: LGPL-3.0
