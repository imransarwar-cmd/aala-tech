# DVZ Sales Order Lock Control — strict Closed orders

Technical module: `dvz_sale_order_lock`  
Version: **19.0.1.2.0**  
Target: Odoo 19

## What this update fixes

Version 19.0.1.1.0 deliberately exempted the lock-management group from its
Closed-order checks. It also returned an empty native protected-fields list
for that group. As a result, a user in that group could still add or edit SO
lines while the ribbon said Closed.

**This release changes that policy: Closed means read-only for everyone.**
The group authorizes closing and reopening, NOT editing a closed order. A user
must first reopen the order in a separate operation, then edit and close it again.

| Operation | Ordinary Sales user | Lock-management group |
|---|---|---|
| Edit an Open SO | Normal Odoo access rules | Normal Odoo access rules |
| Close / Lock | Not allowed | Allowed on a confirmed SO |
| Change Closed SO fields | Blocked | Blocked |
| Add a product, section, subsection or note while Closed | Blocked | Blocked |
| Edit, reorder, move or remove a Closed SO line | Blocked | Blocked |
| Reopen / Unlock | Not allowed | Allowed |

The same restrictions apply to explicit ORM calls, imports and direct line-model
operations. A `sudo()` call alone does not permit editing closed business data.
A combined request to unlock and edit is rejected: reopening must happen first.
Normal Odoo ACLs, record rules and native confirmed/delivered/invoiced-line
restrictions still apply after reopening.

## Existing layout and data are retained

- Closed red ribbon / Open green ribbon on the form; no visible header badge.
- SO Status immediately after Odoo's native Status in the order/quotation lists.
- Open / Closed search filters and grouping.
- Same `sale.order.locked` field, computed status field, model names and XML IDs.
- No SQL data migration, deletion, unlocking of existing orders or new tables.
- No edits to Odoo source files, POS modules, or unrelated custom addons.

The group display label changes from **Manage Lock / Edit Locked Orders** to
**Manage Lock / Reopen Orders**. Its XML ID remains:

`dvz_sale_order_lock.group_manage_locked_sale_orders`

Existing group memberships are retained. The technical helper method
`_dvz_is_locked_editor()` is kept for compatibility but now authorizes lock
transitions only; it is not an editing exemption.

## Upgrade the existing addon

This is the SAME addon, not a second extension to install alongside v1.1.

1. Back up the database and existing addon. Test on a duplicate/local database.
2. Replace the complete `dvz_sale_order_lock` folder in the addons path used by
   your active Odoo instance. Do not leave another copy earlier in addons_path.
3. Restart all workers of that instance so the Python guards are reloaded.
4. In Apps, find **DVZ Sales Order Lock Control** and choose **Upgrade**.
5. Confirm version **19.0.1.2.0**, then refresh/reopen the SO form.

Do NOT uninstall. An XML-only change or a browser refresh is not sufficient
because this release changes Python create/write/unlink checks as well.

Command-line equivalent, using your own correct paths and a stopped test instance:

```bash
/path/to/venv/bin/python3 /path/to/odoo-bin \
  -c /path/to/odoo.conf -d YOUR_TEST_DATABASE \
  -u dvz_sale_order_lock --stop-after-init \
  --no-http --workers=0 --max-cron-threads=0 \
  --logfile=/dev/stdout
```

Run the command as the same OS account and with the same Python environment as
the Odoo service. Do not upgrade a database concurrently with another running
Odoo process. Restart the regular service only after a successful upgrade.

## Daily workflow

**Open → edit → Close / Lock → read-only → authorized Reopen / Unlock → edit.**

Give **Sales Order Lock → Manage Lock / Reopen Orders** only to approved users.
It does not give access to other users' or companies' documents that their normal
Sales rules restrict. Server superuser mode can perform a lock transition, but
cannot edit business data while it remains Closed through these guarded methods.

## Scope and operational implications

All explicit writes on `sale.order` and create/write/unlink on `sale.order.line`
are guarded, including custom fields, M2M choices, sections/notes, ordering,
independent line access and parent One2many commands. Standard custom product
attribute values attached to sales lines are guarded too. The complete
`order_line` widget is read-only when closed, so standard add/delete controls
must be unavailable; server guards provide enforcement even through an API.

This is an **editing lock, not a historical snapshot**. Native computed values
such as delivered/invoiced quantities may still change through Odoo's ORM
recomputation. Narrow, private server-only scopes allow native confirmation-mail
metadata and portal-token initialization; they never allow changing lines,
prices, quantities, custom fields or customer details.

Workflows that explicitly add or change SO lines (for example a down-payment
line, expense reinvoicing or a third-party integration) must first reopen the
order, even when run with elevated privileges. Test your actual invoice,
delivery, mail and custom workflows on staging. No blanket privilege/context
bypass is provided.

Customer/product/project master records and independent custom child models are
not globally locked. Their ACLs remain separate. A malicious server addon that
bypasses the ORM, or direct database changes by an administrator, is outside this
module's protection. Chatter/attachments are separate models; this module does
not promise all third-party chatter integrations are compatible.

## Tests

Run the isolated regression suite (Python and lxml, no Odoo required):

```bash
python3 -m unittest discover -s dvz_sale_order_lock/qa -v
```

There are also Odoo `TransactionCase` tests in `tests/`. Use a disposable Odoo 19
database, never production:

```bash
python3 odoo-bin -c /path/to/test.conf -d TEST_DATABASE \
  -u dvz_sale_order_lock --test-tags /dvz_sale_order_lock \
  --stop-after-init --workers=0 --max-cron-threads=0 \
  --http-interface=127.0.0.1 --http-port=8097 --logfile=/dev/stdout
```

Use `-i` instead of `-u` for a fresh installation. Choose a free test port.
See `docs/TEST_REPORT.md` for executed checks versus tests NOT run, and
`docs/ACCEPTANCE_TESTS.md` for the browser acceptance checklist.
