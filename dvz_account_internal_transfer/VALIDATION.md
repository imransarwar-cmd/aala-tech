# Validation status — 19.0.1.2.1

## Completed in the preparation environment

- Python syntax parsed successfully for model, package, manifest and integration-test files.
- All three XML files are well-formed.
- Every manifest data path exists.
- XML object-button method names and model field references were checked against the model.
- The bridge field has neither a field-level default nor a NOT NULL requirement, avoiding a false bridge assignment to historical records during schema initialization.
- The reversal code path uses the original saved account.move rather than recalculating from current journal default accounts.
- **61 isolated tests passed** in this preparation environment. The original 30 tests cover all four bank/cash combinations, four-line payloads, source/destination preservation, bridge net-zero arithmetic, line currencies, no tax defaults, rounding, invalid/missing bridge selection, duplicate liquidity accounts, wrong companies, foreign-currency accounts, invalid amounts, edit protection, and the scope of bridge-line selection.
- The 31 added checks cover matching model/form domains, Current Assets and reconciliation eligibility, exclusion of other account types, active/company filtering, company changes, disabled inline account creation, eligible company defaults, invalid company defaults, and missing defaults. Domain checks inspect the actual source and form XML, then evaluate their literal conditions; they do not simulate the browser.
- Relative to 19.0.1.2.0, the model's only method change is eligibility filtering in `_company_bridge_account()`. All field definitions and the posting, reversal, validation and source/destination selection methods are unchanged.

The isolated tests do **not** execute Odoo's real ORM, PostgreSQL, access-control engine, journal posting, reconciliation engine, reversal engine or UI. A passing local test is not evidence of successful installation in an Odoo database.

## Included but not executed here

There are **13 Odoo database integration tests** in `tests/test_internal_transfer.py`, including actual posting, bridge reconciliation, reversal, old two-line records, changed journal default accounts, duplicate-post prevention, posted-record protection and copying a posted transfer to a new draft.

Odoo is not installed in the preparation environment. Installation/upgrade, PostgreSQL behavior, company access rules, concurrent actions, localization interactions and compatibility with the installed `base_accounting_kit` version remain to be verified on staging.

## Reproduce isolated tests

Run this in a separate Python process with pytest installed; do not import the substitute Odoo modules into a real Odoo server process:

```bash
python -m pytest -q dvz_account_internal_transfer/tools/validate_isolated.py
```

## Staging acceptance checks

1. Back up and restore a copy of the current database and filestore into staging; upgrade the same addon there.
2. Confirm installed version 19.0.1.2.1, reload the form, and verify source/destination journal choices are unchanged.
3. Check both the bridge dropdown and Search More: only active Current Assets accounts with Allow Reconciliation enabled for the selected company should appear. Confirm a non-reconcilable Current Assets account and a Bank and Cash account do not appear. Confirm an ineligible company-configured default is not preselected. Configure/select a suitable bridge account.
4. Test bank-to-bank, bank-to-cash, cash-to-bank and cash-to-cash transfers.
5. Check one four-line entry: bridge debit / source credit / destination debit / bridge credit. Both bridge lines must be reconciled and net to zero.
6. Reverse a new transfer and confirm each account nets to zero across original and reversal.
7. Open and reverse a historical two-line transfer; it must not acquire extra bridge lines.
8. Verify a second post/reversal is rejected, and that users cannot edit a posted transfer.
9. Verify company isolation and normal permitted Accounting Manager access in the deployed database.
10. Confirm your bank statement import/matching process does not create a duplicate transfer.

See README.md for scope, account setup, upgrade instructions and limitations.
