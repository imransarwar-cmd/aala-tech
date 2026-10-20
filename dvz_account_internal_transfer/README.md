# DVZ Internal Bank and Cash Transfers — Odoo 19

Version 19.0.1.1.0. Upgrade the existing module (do not uninstall).

Changes: Odoo 19-compatible optional account field checks, automatic transfer references TRF/YYYY/00001, mail chatter and activities, tracking of state/name. Existing records and journal entries are retained. Previously created transfer names remain unchanged; new records get sequence numbers.

**Accounting:** This module creates one balanced miscellaneous journal entry directly between the two journal default accounts. It does not automatically match/reconcile bank statement lines. Test accounting treatment with your accountant before production.

**Upgrade:** Back up database, replace addon folder, restart Odoo, upgrade addon in Apps. No database migration or deletion is required.
