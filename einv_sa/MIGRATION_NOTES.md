# einv_sa: v16 → v19 migration notes

## Fixed (syntax/API breakages that would prevent install)

1. **`model/account_move.py`** — removed the import
   `from odoo.addons.web.controllers.main import Action, Home, ensure_db`
   and the `Home` override that stripped `X-Frame-Options` from `/web/login`.
   - That import path was removed from Odoo years ago (`Home` moved to
     `odoo.addons.web.controllers.home` back in v15) — it would raise
     `ImportError` on load and crash the whole module.
   - The override itself has nothing to do with e-invoicing; it disabled
     clickjacking protection on the login page for every user of the
     database. Not something that should ship silently inside a tax module.
     If you need iframe embedding of the login page, do that separately and
     deliberately.

2. **`model/*.py`** — removed unused `from odoo.exceptions import UserError, Warning`
   imports where neither was actually used, and dropped `Warning` (a
   deprecated `UserError` alias) everywhere.

3. **`model/account_move.py` `_post()`** — changed
   `def _post(self, soft=True): super()._post(soft)` to
   `def _post(self, *args, **kwargs): super()._post(*args, **kwargs)`.
   I could not verify the exact v19 signature against your actual server
   source, so this pass-through version is safer than assuming `soft=True`
   still exists.

4. **`view/partner.xml`, `view/account_move_views.xml`** — replaced all
   `attrs="{...}"` with direct field expressions (`invisible="..."`,
   `required="..."`, `readonly="..."`). `attrs`/`states` were **removed
   entirely in Odoo 17** — any view using them fails to load.

5. **`view/partner.xml`** — Bootstrap classes `mr-2`/`mr-3` → `me-2`/`me-3`
   (Odoo 17+ ships Bootstrap 5; `mr-*`/`ml-*` no longer exist).

6. **`__manifest__.py`** — version bumped to `19.0.1.0.0` (Odoo convention).

## Needs your judgment / verification against your actual v19 install

**This is the important one.** The report (`report/account_move.xml` line
44) renders the QR code from `doc.l10n_sa_qr_code_str` — **not** from this
module's own `einv_sa_qr_code_str` field (that one is computed but never
displayed; looks like dead code left over from a previous "fix conflict
with odoo e-invoice" patch mentioned in the changelog).

`l10n_sa_qr_code_str` is a field from Odoo's **native** Saudi Arabia
localization. By v19, Odoo's built-in ZATCA support (`l10n_sa`,
`l10n_sa_edi`, `l10n_sa_edi_pos`) is far more complete than it was in v16 —
it now covers Phase 2 e-invoicing with live Fatoora portal integration, and
per Odoo's own v19 docs it already provides address fields like District
and Building Number on partner/company records.

That means, before installing this module on your v19 system, you should:

- Check whether `l10n_sa` is already installed and whether it already
  defines `building_no`, `district`, `additional_no`, `other_id` (or
  equivalents) on `res.partner`/`res.company` — if so, this module's
  versions will clash or become redundant.
- Add `l10n_sa` to `depends` in the manifest if you keep relying on
  `l10n_sa_qr_code_str` (I added a comment there rather than adding the
  dependency outright, since it changes what this module assumes about
  your setup).
- Decide whether you actually need this third-party module at all for
  production ZATCA compliance in v19, versus just configuring Odoo's
  native Saudi Arabia localization, which is now the "real" compliance
  path (talks to ZATCA's Fatoora portal directly).

**Other things to verify on your actual server** (I don't have access to
your v19 source, so these need a real test install):

- `view/partner.xml` xpaths target `//field[@name='zip']`,
  `//field[@name='city']`, `//field[@name='state_id']`,
  `//field[@name='country_id']`, `//field[@name='street2']`,
  `//field[@name='vat']` inside `base.view_partner_form`. Odoo's address
  block layout has been reshuffled across versions — if any of these
  xpaths don't match, the view will fail to load with a `ParseError`
  naming the missing xpath.
- There's a **pre-existing logic bug**, not something I introduced: in
  `_post()`, the check
  `if not record.einv_sa_show_delivery_date: raise UserError('Delivery Date cannot be empty')`
  actually validates the wrong field — `einv_sa_show_delivery_date` is a
  computed boolean that's just "is this an SA out-invoice", not whether a
  delivery date was entered. It probably should check
  `record.einv_sa_delivery_date` instead. Left as-is since it's a business
  logic question, not a version-compat one — flagging it so it doesn't
  surprise you in testing.

## Recommended install process

1. Install on a **staging/test database** first, not production.
2. Watch server logs closely on install (`sudo journalctl -u odoo19 -f`).
3. Print a test invoice for a Saudi customer immediately after install to
   confirm the QR code renders and the partner form doesn't break.
