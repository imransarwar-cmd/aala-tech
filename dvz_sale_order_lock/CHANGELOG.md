# Changelog

## 19.0.1.2.0 — strict Closed state

- Closed SOs and lines are read-only for every user, including the lock group.
- Group/sudo no longer exempts explicit business edits, line creation/deletion,
  reordering, reparenting or custom product attribute changes.
- Retain native `_get_protected_fields()` rather than overriding it with [].
- Allow the group to change the lock alone; reject combined unlock-and-edit writes.
- Set the full `order_line` One2many widget read-only on Closed orders.
- Preserve all ribbon/list/filter/grouping changes from v1.1.
- Rename the group label to Manage Lock / Reopen Orders without changing its XML ID.
- Keep narrow internal metadata scopes for native confirmation email cleanup and
  portal-token generation, not commercial-data edits.
- Extend regressions for authorized users, explicit sudo, command batches,
  custom fields, reparenting, separate reopen and native line protection.

## 19.0.1.1.0 — layout only (superseded)

Replaced the header badge with ribbons and moved SO Status after native Status.
This version still let authorized users edit while Closed.

## 19.0.1.0.0 — initial release (superseded)

Group-controlled SO locking, stored Open/Closed status, filters and grouping.
