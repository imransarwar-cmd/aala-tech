# DVZ Internal Bank and Cash Transfers — Odoo 19

## Version 19.0.1.2.1 — Bridge account dropdown filter

The **Internal Transfer Bridge Account** dropdown and its Search More results are explicitly restricted to accounts that meet all of these conditions:

- Type is **Current Assets** (`account_type = asset_current`).
- **Allow Reconciliation** is enabled (`reconcile = True`).
- Account is **active** and available to the **selected transfer company**.

The previous version already declared this domain in the model. This patch also declares the same domain directly on the transfer form. The company-configured default is now checked against the same conditions before it is preselected; an ineligible or missing company default leaves the bridge field empty for manual selection. Accounts are not reclassified and reconciliation settings are not changed automatically.

Source and destination account selection, the Transfer Entry Journal, posting, reconciliation and reversal logic are unchanged. No migration or automatic rewriting of historical transfers is included.

### Background: 19.0.1.2.0

The preceding revision added the **Internal Transfer Bridge Account** field. Source and destination journals continue to use their existing Default Accounts, and the single-entry workflow is retained.

### Posting example: 1,000 in the company currency

| Leg | Account | Debit | Credit |
|---|---|---:|---:|
| Source to bridge | Internal Transfer Bridge Account | 1,000 | 0 |
| Source to bridge | Source bank/cash account | 0 | 1,000 |
| Bridge to destination | Destination bank/cash account | 1,000 | 0 |
| Bridge to destination | Internal Transfer Bridge Account | 0 | 1,000 |

One miscellaneous journal entry contains all four lines. The two bridge lines are automatically reconciled with each other. The net effect is source -1,000, destination +1,000 and bridge zero. The entry's gross debit and credit totals are each 2,000; that is expected because it records two legs, not a 2,000 transfer.

Both legs post together on the same date. This is **not** a two-date funds-in-transit workflow, and it does not create separate entries in the source/destination journals.

## Bridge account setup

Use an existing appropriate clearing account, or have the accounting administrator create one in Accounting > Configuration > Chart of Accounts:

- Name: **Internal Transfer Bridge Account** (or the existing equivalent).
- Code: choose an unused code consistent with your own chart of accounts; no code is invented by the module.
- Type: **Current Assets**.
- **Allow Reconciliation**: enabled.
- Company: the selected transfer company.
- Currency: unset or the company's currency.

Then select that account in the new field on the Internal Transfer form. The dropdown intentionally does not create ledger accounts inline.

New transfers default to the company's existing `transfer_account_id` (Inter-Banks Transfer Account) only when it meets the dropdown conditions above. The module does not create or rename any ledger account, or change that company setting. It does not silently reuse an account merely because its name matches.

The bridge must differ from both liquidity accounts. An archived, wrong-company, non-reconcilable, non-Current-Assets or foreign-currency bridge is rejected.

## Upgrade — do not uninstall

1. Back up the database and filestore; first test on a restored staging database.
2. Replace the existing `dvz_account_internal_transfer` addon directory with the folder in this ZIP. Keep the same technical module name.
3. Restart Odoo and **upgrade** the existing module from Apps, or use your normal Odoo upgrade command. Confirm the installed version is **19.0.1.2.1**, then reload the browser form.
4. Open a new or unposted draft internal transfer and select the bridge account. An older draft may need it selected manually. If the list is empty, have the accounting administrator confirm that an appropriate account meets all four filter conditions; this patch does not create one.
5. Post a small test transfer, check the four journal items and bridge reconciliation, then test the reversal.

Historical posted/reversed entries are not rewritten or reposted. The new database field is nullable without a field-level default, so old two-line transfers are not backfilled as though they used a bridge. They display a legacy notice. Reversals use Odoo's actual original journal-entry lines, including for legacy transfers, rather than rebuilding the entry from current journal defaults.

Existing transfer references and sequence records are retained. Duplicating a transfer starts a new draft with a new reference and no journal-entry links.

## Scope and safeguards

- Same-company, company-currency transfers only; foreign-currency journal/account configurations are blocked when posting. No exchange-rate or intercompany accounting is implemented.
- Both transfer legs are posted atomically; the same transfer cannot be posted twice through this workflow.
- Posted/reversed transfer business fields cannot be edited through this model.
- Posting/reversal is restricted to Accounting Managers; records are limited to enabled companies.
- Keep the existing `base_accounting_kit` and `mail` dependencies. This package does not include or replace them.
- This does **not** initiate a real bank transfer, create payments, import statements, or automatically match bank-statement lines. Automatic matching applies only to the two bridge lines in this entry.
- Do not independently categorize imported bank statement transactions as another new transfer; that can duplicate the ledger effect. Review the matching procedure with the accounting administrator.
- A reversal does not undo existing bank-statement matching. Review previously reconciled bank transactions before reversing.
- Do not reset or edit the generated journal entry independently of the transfer workflow; the module does not continuously synchronize transfer status with manual changes to journal entries.

## Testing

See `VALIDATION.md`. Local isolated logic tests and syntax checks are not a substitute for an installed Odoo 19 database test. Odoo integration tests are included under `tests/` but were not executed in the preparation environment.

Example staging-only test invocation (adapt executable, database and addons paths):

```bash
./odoo-bin -d YOUR_STAGING_DB -u dvz_account_internal_transfer \
  --test-enable --test-tags /dvz_account_internal_transfer --stop-after-init
```

## Technical references

Odoo 19 official source reviewed for this patch:

- Company transfer-account field and domain: https://github.com/odoo/odoo/blob/19.0/addons/account/models/company.py
- Account fields (`active`, `company_ids`, `reconcile`, `account_type`): https://github.com/odoo/odoo/blob/19.0/addons/account/models/account_account.py
- Original-entry reversal method: https://github.com/odoo/odoo/blob/19.0/addons/account/models/account_move.py
- Journal-item reconciliation: https://github.com/odoo/odoo/blob/19.0/addons/account/models/account_move_line.py

The chosen four-line miscellaneous-entry workflow is this custom module's design; it is not a claim that this reproduces Odoo's bank-statement internal-transfer workflow.
