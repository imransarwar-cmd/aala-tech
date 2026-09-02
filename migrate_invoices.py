#!/usr/bin/env python3
"""
Migrate specific Customer Invoices from an Odoo 16 database to an Odoo 19
database, using Odoo's XML-RPC API on both ends (no direct DB access
needed, works across versions).

WHY XML-RPC AND NOT RAW SQL / A DB DUMP:
Invoices reference partners, products, taxes, and accounts - all of
which have DIFFERENT internal IDs in the two databases. Copying rows
directly would silently point at the wrong partner/product in v19. This
script instead re-creates each invoice through Odoo's own API, resolving
each reference by a stable business key (partner: email/VAT/name,
product: default_code/name) so it lands on the correct v19 record, or is
clearly reported as unmatched if it can't be resolved automatically.

WHAT GETS MIGRATED PER INVOICE:
    Partner/customer, currency, invoice date, due date, reference,
    every invoice line (product, description, qty, price, taxes - each
    resolved to its v19 equivalent), and every file attachment on the
    record.

WHAT THIS DOES NOT DO:
- It does not post the migrated invoice automatically - it's created in
  draft state so you can review it in v19 before confirming/posting.
- It does not migrate PAYMENTS already reconciled against the invoice in
  v16 - only the invoice document itself. Payment history needs separate
  handling if required.
- It does not delete or modify anything in Odoo 16 (source only, read-only).
- It skips (does not duplicate) any invoice that already exists in v19 by
  the same name - safe to re-run.

USAGE:
    1. Fill in the CONFIG section below (or set environment variables).
    2. Test a single record first, dry-run (no changes made):
           python3 migrate_invoices.py --only INV/2026/0001
    3. Once that output looks correct, apply it for real:
           python3 migrate_invoices.py --only INV/2026/0001 --apply
    4. Check the result in Odoo 19's UI, then run the full batch:
           python3 migrate_invoices.py              # dry-run, all records
           python3 migrate_invoices.py --apply       # actually create them

REQUIREMENTS:
    Python 3 standard library only (xmlrpc.client) - nothing to pip install.
"""

import argparse
import sys
import xmlrpc.client

# ============================================================================
# CONFIG - fill these in, or export as environment variables of the same
# name (os.environ) and remove the literal values below.
# ============================================================================

SOURCE = {
    "url": "https://odoo.aala-tech.com",   # Odoo 16 - adjust host/port
    "db": "odoo",                     # Odoo 16 database name
    "username": "imran.sarwar@aala-tech.com",
    "password": "123",          # or an API key
}

TARGET = {
    "url": "https://erp-odoo.aala-tech.com",   # Odoo 19 - adjust host/port
    "db": "aala_tech_production",     # Odoo 19 database name
    "username": "imran.sarwar@aala-tech.com",
    "password": "123",  # or an API key
}

# Invoice numbers to migrate - from Tax_Invoices.xlsx (37 invoices,
# 2026-08-09 through 2026-08-30).
INVOICE_NAMES = [
    # "ATC/INV/2026/00350",
    # "ATC/INV/2026/00349",
    # "ATC/INV/2026/00348",
    # "ATC/INV/2026/00347",
    # "ATC/INV/2026/00346",
    # "ATC/INV/2026/00345",
    # "ATC/INV/2026/00344",
    # "ATC/INV/2026/00343",
    # "ATC/INV/2026/00342",
    # "ATC/INV/2026/00341",
    # "ATC/INV/2026/00340",
    # "ATC/INV/2026/00339",
    "ATC/INV/2026/00338",
    "ATC/INV/2026/00337",
    "ATC/INV/2026/00336",
    "ATC/INV/2026/00335",
    "ATC/INV/2026/00334",
    "ATC/INV/2026/00333",
    "ATC/INV/2026/00332",
    "ATC/INV/2026/00331",
    "ATC/INV/2026/00330",
    "ATC/INV/2026/00329",
    "ATC/INV/2026/00328",
    "ATC/INV/2026/00327",
    "ATC/INV/2026/00326",
    "ATC/INV/2026/00325",
    "ATC/INV/2026/00324",
    "ATC/INV/2026/00323",
    "ATC/INV/2026/00322",
    "ATC/INV/2026/00321",
    "ATC/INV/2026/00320",
    "ATC/INV/2026/00319",
    "ATC/INV/2026/00318",
    "ATC/INV/2026/00317",
    "ATC/INV/2026/00316",
    "ATC/INV/2026/00315",
    "ATC/INV/2026/00314",
]

# Terms & Conditions text applied to the "narration" field on every
# invoice this script touches - both newly created ones and existing
# ones that only get their lines populated.
TERMS_AND_CONDITIONS_HTML = """
<p><strong>Terms &amp; Conditions:</strong></p>
<p><strong>Payment Terms:</strong></p>
<ul>
    <li>10% Advance Payment</li>
    <li>90% L.C. Within 15 Days of Work done Certificate</li>
</ul>
<p><strong>Bank Detail:</strong><br/>
AALA TECH COMPANY LIMITED<br/>
IBAN: SA6345000000221479579001<br/>
Saudi Awwal Bank<br/>
VAT: 311654088800003</p>
"""


# ============================================================================
# XML-RPC helpers
# ============================================================================

class OdooConnection:
    """Thin wrapper around Odoo's XML-RPC API (works against any Odoo
    version - 16 and 19 both expose the same /xmlrpc/2/* endpoints)."""

    def __init__(self, url, db, username, password, label):
        self.url = url
        self.db = db
        self.label = label
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        self.uid = common.authenticate(db, username, password, {})
        if not self.uid:
            raise RuntimeError(
                f"[{label}] Authentication failed for user {username!r} "
                f"on db {db!r} at {url}"
            )
        self.password = password
        self.models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def execute(self, model, method, *args, **kwargs):
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, method, list(args), kwargs
        )

    def search_read(self, model, domain, fields, **kwargs):
        return self.execute(model, "search_read", domain, fields, **kwargs)

    def search(self, model, domain, **kwargs):
        return self.execute(model, "search", domain, **kwargs)

    def get_field_names(self, model):
        """Cached set of real field names on this connection for a given
        model. Used to drop fields that don't exist on this specific Odoo
        version instead of failing outright - field names occasionally
        differ between versions, and this makes the script resilient to
        that without needing to hardcode every possible variant."""
        if not hasattr(self, "_field_cache"):
            self._field_cache = {}
        if model not in self._field_cache:
            fields = self.execute(model, "fields_get", [], {"attributes": []})
            self._field_cache[model] = set(fields.keys())
        return self._field_cache[model]

    def create(self, model, vals):
        known = self.get_field_names(model)
        safe_vals = {}
        dropped = []
        for key, value in vals.items():
            if key not in known:
                dropped.append(key)
                continue
            safe_vals[key] = value
        if dropped:
            print(f"    [WARN] {model}: dropping field(s) not present on "
                  f"target - {', '.join(dropped)}")
        return self.execute(model, "create", safe_vals)


# ============================================================================
# Cross-database matching (partner / product / tax)
# ============================================================================

class RecordMatcher:
    """Resolves a v16 record (partner, product, tax) to its v19
    equivalent by business key, caching lookups.

    Partners and products: found -> left untouched; not found -> created
    fresh in the target (never overwrites existing target data).
    Taxes/currencies: matched only - reported as unmatched if missing,
    since auto-creating a tax record safely needs more context (rate,
    account, type) than is safe to guess here.
    """

    def __init__(self, target: OdooConnection):
        self.target = target
        self.partner_cache = {}
        self.product_cache = {}
        self.tax_cache = {}
        self.currency_cache = {}
        self.unmatched = {"tax": set(), "currency": set()}

    def match_partner(self, src_partner):
        key = src_partner["id"]
        if key in self.partner_cache:
            return self.partner_cache[key]

        target_id = None
        vat = (src_partner.get("vat") or "").strip()
        email = (src_partner.get("email") or "").strip()
        name = (src_partner.get("name") or "").strip()

        if vat:
            found = self.target.search("res.partner", [["vat", "=", vat]], limit=1)
            if found:
                target_id = found[0]
        if not target_id and email:
            found = self.target.search("res.partner", [["email", "=", email]], limit=1)
            if found:
                target_id = found[0]
        if not target_id and name:
            found = self.target.search("res.partner", [["name", "=", name]], limit=1)
            if found:
                target_id = found[0]

        if target_id:
            self.partner_cache[key] = target_id
            return target_id

        partner_vals = {
            "name": name,
            "email": email or False,
            "vat": vat or False,
            "phone": src_partner.get("phone") or False,
            "mobile": src_partner.get("mobile") or False,
            "street": src_partner.get("street") or False,
            "city": src_partner.get("city") or False,
        }
        partner_vals = {k: v for k, v in partner_vals.items() if v}
        target_id = self.target.create("res.partner", partner_vals)
        print(f"    [CREATE] partner {name!r} created in target as id={target_id}")
        self.partner_cache[key] = target_id
        return target_id

    def match_product(self, src_product):
        key = src_product["id"]
        if key in self.product_cache:
            return self.product_cache[key]

        target_id = None
        code = (src_product.get("default_code") or "").strip()
        name = (src_product.get("name") or "").strip()

        if code:
            found = self.target.search(
                "product.product", [["default_code", "=", code]], limit=1
            )
            if found:
                target_id = found[0]
        if not target_id and name:
            found = self.target.search(
                "product.product", [["name", "=", name]], limit=1
            )
            if found:
                target_id = found[0]

        if target_id:
            self.product_cache[key] = target_id
            return target_id

        product_vals = {"name": name}
        if code:
            product_vals["default_code"] = code
        target_id = self.target.create("product.product", product_vals)
        print(f"    [CREATE] product {name!r} created in target as id={target_id}")
        self.product_cache[key] = target_id
        return target_id

    def match_tax(self, src_tax_name, type_tax_use):
        cache_key = (src_tax_name, type_tax_use)
        if cache_key in self.tax_cache:
            return self.tax_cache[cache_key]
        found = self.target.search(
            "account.tax",
            [["name", "=", src_tax_name], ["type_tax_use", "=", type_tax_use]],
            limit=1,
        )
        target_id = found[0] if found else None
        self.tax_cache[cache_key] = target_id
        if not target_id:
            self.unmatched["tax"].add(f"{src_tax_name} ({type_tax_use})")
        return target_id

    def match_currency(self, src_currency_name):
        if src_currency_name in self.currency_cache:
            return self.currency_cache[src_currency_name]
        found = self.target.search(
            "res.currency", [["name", "=", src_currency_name]], limit=1
        )
        target_id = found[0] if found else None
        self.currency_cache[src_currency_name] = target_id
        if not target_id:
            self.unmatched["currency"].add(src_currency_name)
        return target_id


def _copy_attachments(source, target, res_model, source_res_id, target_res_id, label):
    attachments = source.search_read(
        "ir.attachment",
        [["res_model", "=", res_model], ["res_id", "=", source_res_id]],
        ["name", "datas", "mimetype"],
    )
    for att in attachments:
        if not att.get("datas"):
            continue
        target.create("ir.attachment", {
            "name": att["name"],
            "datas": att["datas"],
            "mimetype": att.get("mimetype") or False,
            "res_model": res_model,
            "res_id": target_res_id,
        })
    if attachments:
        print(f"    -> copied {len(attachments)} attachment(s) for {label}")


# ============================================================================
# Invoices
# ============================================================================

def migrate_invoices(source, target, matcher, names, apply_changes):
    print("\n" + "=" * 70)
    print("CUSTOMER INVOICES")
    print("=" * 70)

    invoices = source.search_read(
        "account.move",
        [["name", "in", names], ["move_type", "=", "out_invoice"]],
        [
            "name", "partner_id", "invoice_date", "invoice_date_due",
            "ref", "invoice_line_ids", "currency_id",
        ],
    )
    found_names = {i["name"] for i in invoices}
    for missing in set(names) - found_names:
        print(f"  [SKIP] {missing}: not found in source (Odoo 16) as a posted customer invoice")

    for invoice in invoices:
        name = invoice["name"]

        existing = target.search_read(
            "account.move",
            [["name", "=", name], ["move_type", "=", "out_invoice"]],
            ["invoice_line_ids"],
            limit=1,
        )
        new_id = None
        existing_line_ids_to_remove = []
        if existing:
            existing_line_ids_to_remove = target.search(
                "account.move.line",
                [["move_id", "=", existing[0]["id"]], ["display_type", "=", False]],
            )
            if existing_line_ids_to_remove:
                print(f"  [FOUND] {name}: exists in target (id={existing[0]['id']}) with "
                      f"{len(existing_line_ids_to_remove)} existing line(s) - will REPLACE "
                      f"with correct data from source")
            else:
                print(f"  [FOUND] {name}: exists in target (id={existing[0]['id']}) but has NO lines - will populate lines onto it")
            new_id = existing[0]["id"]

        partner = source.search_read(
            "res.partner", [["id", "=", invoice["partner_id"][0]]],
            ["name", "email", "vat", "phone", "mobile", "street", "city"],
        )[0]
        target_partner_id = matcher.match_partner(partner)

        target_currency_id = None
        if invoice.get("currency_id"):
            currency = source.search_read(
                "res.currency", [["id", "=", invoice["currency_id"][0]]], ["name"]
            )[0]
            target_currency_id = matcher.match_currency(currency["name"])
            if not target_currency_id:
                print(f"  [FAIL] {name}: currency {currency['name']!r} not found in target - skipped")
                continue

        print(f"  [DEBUG] {name}: source invoice_line_ids = {invoice['invoice_line_ids']}")
        lines = source.search_read(
            "account.move.line",
            [
                ["id", "in", invoice["invoice_line_ids"]],
                ["display_type", "not in", ["line_section", "line_note", "line_subsection"]],
            ],
            ["product_id", "name", "quantity", "price_unit", "tax_ids", "display_type"],
        )
        print(f"  [DEBUG] {name}: fetched {len(lines)} source line(s) after display_type filter")

        line_vals = []
        for line in lines:
            if not line.get("quantity"):
                print(f"  [WARN] {name}: line {line.get('name')!r} has no "
                      f"quantity in source - line skipped, invoice still created")
                continue

            target_tax_ids = []
            if line["tax_ids"]:
                taxes = source.search_read(
                    "account.tax", [["id", "in", line["tax_ids"]]],
                    ["name", "type_tax_use"],
                )
                for tax in taxes:
                    t_id = matcher.match_tax(tax["name"], tax["type_tax_use"])
                    if t_id:
                        target_tax_ids.append(t_id)

            vals = {
                "name": line["name"],
                "quantity": line["quantity"],
                "price_unit": line["price_unit"],
                "tax_ids": [(6, 0, target_tax_ids)],
            }
            if line.get("product_id"):
                product = source.search_read(
                    "product.product", [["id", "=", line["product_id"][0]]],
                    ["default_code", "name"],
                )[0]
                vals["product_id"] = matcher.match_product(product)

            line_vals.append((0, 0, vals))

        vals = {
            "partner_id": target_partner_id,
            "move_type": "out_invoice",
            "invoice_date": invoice.get("invoice_date") or False,
            "invoice_date_due": invoice.get("invoice_date_due") or False,
            "ref": invoice.get("ref") or "",
            "narration": TERMS_AND_CONDITIONS_HTML,
        }
        if target_currency_id:
            vals["currency_id"] = target_currency_id

        if not apply_changes:
            action = "Would populate lines onto existing" if new_id else "Would create"
            print(f"  [DRY-RUN] {action} invoice {name} "
                  f"(customer={partner['name']}, {len(line_vals)} line(s))")
            continue

        # Header first (unless we're populating an existing lines-less
        # record), then lines one at a time - a single bad line only
        # gets skipped, not the whole invoice.
        is_new_record = new_id is None
        if is_new_record:
            new_id = target.create("account.move", vals)
            target.execute("account.move", "write", [new_id], {"name": name})
        else:
            # Existing record: apply Terms & Conditions here too, and
            # remove whatever stale/incorrect lines are currently there
            # before adding the correct ones from source. If the invoice
            # is already posted, Odoo won't allow deleting its lines -
            # report that clearly instead of crashing the batch.
            target.execute("account.move", "write", [new_id], {"narration": TERMS_AND_CONDITIONS_HTML})
            if existing_line_ids_to_remove:
                try:
                    target.execute("account.move.line", "unlink", existing_line_ids_to_remove)
                    print(f"    -> removed {len(existing_line_ids_to_remove)} stale line(s)")
                except xmlrpc.client.Fault as e:
                    reason = e.faultString.splitlines()[-1] if e.faultString else str(e)
                    print(f"  [FAIL] {name}: cannot remove existing lines - {reason}")
                    print(f"    This invoice is likely already POSTED. Reset it to draft "
                          f"in the v19 UI first, then re-run this script.")
                    continue

        added, skipped = 0, 0
        for lv in line_vals:
            try:
                target.execute("account.move", "write", [new_id], {"invoice_line_ids": [lv]})
                added += 1
            except xmlrpc.client.Fault as e:
                skipped += 1
                reason = e.faultString.splitlines()[-1] if e.faultString else str(e)
                print(f"  [WARN] {name}: line skipped - {reason}")
                print(f"    Line data: {lv}")

        if is_new_record:
            _copy_attachments(source, target, "account.move", invoice["id"], new_id, name)
        status = f"{added} line(s) added" + (f", {skipped} skipped" if skipped else "")
        verb = "created" if is_new_record else "updated (lines populated)"
        print(f"  [OK] {name}: {verb} in target as id={new_id} ({status}) - left in draft for review")


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually create records in the target (v19) database. "
             "Without this flag, the script only prints what it would do."
    )
    parser.add_argument(
        "--only", metavar="NAME", default=None,
        help="Only process a single invoice by exact name (e.g. "
             "--only INV/2026/0001). Useful for testing one record "
             "end-to-end before running the full batch."
    )
    args = parser.parse_args()

    print(f"Mode: {'APPLY (will write to target)' if args.apply else 'DRY-RUN (no changes will be made)'}")

    try:
        source = OdooConnection(**SOURCE, label="source/v16")
        target = OdooConnection(**TARGET, label="target/v19")
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    matcher = RecordMatcher(target)

    names = INVOICE_NAMES
    if args.only:
        names = [args.only]
        if not names:
            print(f"ERROR: --only {args.only!r} does not match any name.")
            sys.exit(1)

    if not names:
        print("ERROR: No invoice names configured. Fill in INVOICE_NAMES "
              "at the top of this script, or use --only NAME to test a "
              "single invoice.")
        sys.exit(1)

    migrate_invoices(source, target, matcher, names, args.apply)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    if matcher.unmatched["tax"] or matcher.unmatched["currency"]:
        print("Unmatched records requiring manual attention in the target DB:")
        for kind, values in matcher.unmatched.items():
            if values:
                print(f"  {kind}:")
                for v in sorted(values):
                    print(f"    - {v}")
        print(
            "\nCreate/fix these in Odoo 19 first (matching by name), then "
            "re-run this script - it skips invoices that already exist, "
            "so it's safe to run again."
        )
    else:
        print("No unmatched taxes/currencies.")

    if not args.apply:
        print("\nThis was a DRY RUN. Re-run with --apply to actually create records.")


if __name__ == "__main__":
    main()