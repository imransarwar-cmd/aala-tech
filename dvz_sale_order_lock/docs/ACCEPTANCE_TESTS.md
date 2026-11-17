# Acceptance tests — v19.0.1.2.0

Use a TEST database and two users: a salesperson without the special group and
an approved user in **Manage Lock / Reopen Orders**. Neither needs superuser mode.
Verify the addon installed version is 19.0.1.2.0 and all Odoo workers were restarted.

## Critical regression (perform as the approved lock manager)

1. Create/confirm an SO with a normal product line and a note/section line.
2. While Open, verify normal permitted field/line edits work; save them.
3. Click **Close / Lock**. The ribbon must say Closed.
4. The product/section/note insertion controls must be unavailable.
5. Try product, description, quantity, unit price, discount and custom fields:
   they must be read-only. The line delete control must not be available.
6. Repeat through a separate SO-line form/list if one is used in your system.
   Saving a change through an API/import must be rejected by the server.
7. The header/customer reference and custom SO fields must be read-only too.
8. Click **Reopen / Unlock**. Normal permitted edits work again. Add/edit/delete
   a NOTE line as an uncomplicated deletion test. Native Odoo may prohibit
   deletion of a confirmed product line even after unlocking.
9. Close it again; the protections must return.

## Ordinary salesperson

1. Open the same Closed SO. All the restrictions above must apply.
2. This user must not be able to close/reopen through the buttons or direct API.
3. Have the manager reopen it, then verify the salesperson's normal editing
   permissions return. Reclosing must block them again.

## API/import tests

Against disposable records only, check that Closed orders reject:
- `sale.order.line.create`, including `default_order_id` in context;
- direct line `write` and `unlink`;
- parent `order_line` commands to add/edit/delete/clear/set/link rows;
- moving a line into or out of the Closed SO;
- `write({'locked': False, 'order_line': ...})` in the SAME request;
- ordinary, group-enabled and elevated ORM callers attempting business edits.

Use the included Odoo test class rather than experimenting on real orders.

## Layout / normal workflow regression

- Red Closed / green Open ribbon; no duplicate visible badge in the header.
- SO Status adjacent to native Status in lists; filters and grouping work.
- Existing membership of the renamed lock group is retained.
- Existing closed records remain closed; quantities/prices are unchanged by upgrade.
- Confirm a quotation using your native auto-lock setting.
- Check ordinary invoicing, stock deliveries, portal preview, confirmation mails
  and custom integrations on your test copy. Workflows that insert/change SO
  lines must reopen first; do not treat such a rejection as permission to bypass
  the lock or to delete data.

These browser and live-registry checks were NOT executed in the build environment.
