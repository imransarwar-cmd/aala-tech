#!/usr/bin/env python3
"""
Create CRM Leads/Opportunities (crm.lead) in Odoo 19 from an Excel file,
using Odoo's XML-RPC API (no odoo-bin shell needed - runs with plain
`python3`, same approach as import_purchase_orders.py).

EXPECTED EXCEL LAYOUT (one row per lead - matched by header text in
row 1, so column order doesn't matter):

    Quote | Date | Customer | Project | System | Brand | Area | Sales |
    Value (w/o VAT) | Status | Remarks

    ADJUST THESE HEADER NAMES in EXCEL_COLUMNS below if your actual
    file uses different column titles.

WHAT GETS CREATED/SET PER ROW, ALL DIRECTLY IN ODOO 19 (dvz_crm_ext
module's own fields, see crm_lead.py):
    - Quote          -> stored in the lead's PO - Ref # field (po_ref) -
                        NOT quotation_no.
    - Customer       -> find-or-create res.partner (left ACTIVE)
    - Project        -> find-or-create project.project (dvz_project,
                        many2many)
    - System         -> find-or-create system.master (system_ids,
                        many2many)
    - Brand          -> find-or-create dvz.brand (brand_ids, many2many)
    - Area           -> find-or-create dvz.area (area_ids, many2many)
    - Sales          -> find-or-create hr.employee (sales_ids,
                        many2many) - a NEWLY created one is archived
                        right away (active=False), since a name off an
                        old tracking sheet isn't necessarily a real,
                        current staff member. An employee that ALREADY
                        exists (found by name) is left exactly as-is,
                        active or not - this never archives someone
                        who's genuinely on staff.
    - Status         -> "Won" moves the lead to whichever CRM stage has
                        is_won=True; "Lost" calls the lead's own
                        action_set_lost(); anything else is left as a
                        plain open pipeline lead.
    - Date / Value (w/o VAT) / Remarks map onto inquiry_date /
      expected_revenue / remarks.

WHAT THIS DOES NOT DO:
- Does not connect to any other/source database - Odoo 19 only.
- Skips (does not duplicate) any lead that already has the same value
  in po_ref (i.e. the same "Quote") - safe to re-run after fixing an
  error partway through a batch.
- Does not stop the whole run if one row errors out (bad/missing data,
  a server-side validation error, etc.) - that row is logged as
  failed and skipped, and the script keeps going with the rest. The
  final summary lists exactly which rows failed so you can fix and
  retry just those with --only.

CREDENTIALS:
  Filled in directly in the TARGET dict below - edit url/db/username/
  password to match your real Odoo 19 connection. Each one can still
  be overridden by setting an environment variable of the same name
  (ODOO19_URL, ODOO19_DB, ODOO19_USER, ODOO19_PASSWORD) if you'd
  rather not keep a real password sitting in this file.

USAGE:
    1. Set EXCEL_PATH below to your file's actual path.
    2. Fill in / check the TARGET dict (or export env vars instead).
    3. Test a small slice first, dry-run (no changes made):
           python3 import_legacy_leads.py --limit 3
    4. Once that output looks correct, apply it for real - still just
       that small slice:
           python3 import_legacy_leads.py --limit 3 --apply
    5. Run the full file:
           python3 import_legacy_leads.py              # dry-run, all rows
           python3 import_legacy_leads.py --apply       # actually create them

REQUIREMENTS:
    pip install openpyxl   (xmlrpc.client is Python 3 standard library)
"""

import argparse
import os
import sys
import xmlrpc.client

import openpyxl

# ============================================================================
# CONFIG
# ============================================================================

EXCEL_PATH = "/Users/apple/Documents/odoo-19.0/aala-tech/Quotations Report.xlsx"
SHEET_NAME = None  # e.g. "Sheet1", or None for the active/first sheet

# Header text in row 1 of your Excel file, for each field this script
# needs. Change the VALUES (right side) to match your actual column
# titles - the KEYS (left side) are used internally, don't rename those.
EXCEL_COLUMNS = {
    "quote": "Quote",
    "date": "Date",
    "customer": "Customer",
    "project": "Project",
    "system": "System",
    "brand": "Brand",
    "area": "Area",
    "sales": "Sales",
    "value": "Value (w/o VAT)",
    "status": "Status",
    "remarks": "Remarks",
}


def _require_env(name, default=None):
    value = os.environ.get(name, default)
    if not value:
        sys.exit(
            f"ERROR: {name} is not set (either export it as an "
            f"environment variable, or fill in the TARGET dict directly "
            f"below)."
        )
    return value


# Filled in directly here for convenience - adjust these four values to
# your real Odoo 19 connection details. (An environment variable of the
# same name, if set, overrides whatever's written here.)
TARGET = {
    "url": _require_env("ODOO19_URL", "https://erp-odoo.aala-tech.com"),
    "db": _require_env("ODOO19_DB", "aala_tech_production"),
    "username": _require_env("ODOO19_USER", "imran.sarwar@aala-tech.com"),
    "password": _require_env("ODOO19_PASSWORD", "PUT-YOUR-PASSWORD-OR-API-KEY-HERE"),
}


# ============================================================================
# XML-RPC helper
# ============================================================================

class OdooConnection:
    """Thin wrapper around Odoo's XML-RPC API."""

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

    def create(self, model, vals):
        return self.execute(model, "create", vals)

    def write(self, model, ids, vals):
        return self.execute(model, "write", ids, vals)


# ============================================================================
# Excel reading
# ============================================================================

def read_rows_from_excel(path, sheet_name=None):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet_name] if sheet_name else wb.active

    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    headers = [str(h).strip() if h else "" for h in header_row]

    def col_index(header_text):
        return headers.index(header_text) if header_text in headers else None

    idx = {key: col_index(header) for key, header in EXCEL_COLUMNS.items()}
    if idx["customer"] is None:
        sys.exit(
            "ERROR: required column 'Customer' (or whatever you set "
            "EXCEL_COLUMNS['customer'] to) was not found in row 1 of "
            "the Excel file."
        )

    def cell(excel_row, key):
        i = idx[key]
        return excel_row[i] if i is not None and i < len(excel_row) else None

    rows = []
    for excel_row in ws.iter_rows(min_row=2, values_only=True):
        if not any(excel_row):
            continue  # skip fully blank rows

        date_val = cell(excel_row, "date")
        rows.append({
            "quote": cell(excel_row, "quote"),
            "date": date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else date_val,
            "customer": cell(excel_row, "customer"),
            "project": cell(excel_row, "project"),
            "system": cell(excel_row, "system"),
            "brand": cell(excel_row, "brand"),
            "area": cell(excel_row, "area"),
            "sales": cell(excel_row, "sales"),
            "value": cell(excel_row, "value"),
            "status": cell(excel_row, "status"),
            "remarks": cell(excel_row, "remarks"),
        })
    return rows


# ============================================================================
# find-or-create helpers - one per master-data model this touches
# ============================================================================

class RecordMatcher:
    def __init__(self, target: OdooConnection):
        self.target = target
        self.partner_cache = {}
        self.project_cache = {}
        self.system_cache = {}
        self.brand_cache = {}
        self.area_cache = {}
        self.employee_cache = {}

    def get_or_create_partner(self, name):
        key = name.strip().lower()
        if key in self.partner_cache:
            return self.partner_cache[key]
        found = self.target.search("res.partner", [["name", "=", name]], limit=1)
        if found:
            partner_id = found[0]
        else:
            partner_id = self.target.create("res.partner", {
                "name": name,
                "company_type": "company",
                # so it shows up under the Customer field's own domain
                # filter (customer_rank > 0) in the dvz_crm_ext views
                "customer_rank": 1,
            })
            print(f"    [CREATE] partner {name!r} -> id={partner_id}")
        self.partner_cache[key] = partner_id
        return partner_id

    def get_or_create_project(self, name):
        key = name.strip().lower()
        if key in self.project_cache:
            return self.project_cache[key]
        found = self.target.search("project.project", [["name", "=", name]], limit=1)
        project_id = found[0] if found else self.target.create("project.project", {"name": name})
        if not found:
            print(f"    [CREATE] project {name!r} -> id={project_id}")
        self.project_cache[key] = project_id
        return project_id

    def get_or_create_system(self, name):
        key = name.strip().lower()
        if key in self.system_cache:
            return self.system_cache[key]
        found = self.target.search("system.master", [["name", "=", name]], limit=1)
        system_id = found[0] if found else self.target.create("system.master", {"name": name})
        if not found:
            print(f"    [CREATE] system {name!r} -> id={system_id}")
        self.system_cache[key] = system_id
        return system_id

    def get_or_create_brand(self, name):
        key = name.strip().lower()
        if key in self.brand_cache:
            return self.brand_cache[key]
        found = self.target.search("dvz.brand", [["name", "=", name]], limit=1)
        brand_id = found[0] if found else self.target.create("dvz.brand", {"name": name})
        if not found:
            print(f"    [CREATE] brand {name!r} -> id={brand_id}")
        self.brand_cache[key] = brand_id
        return brand_id

    def get_or_create_area(self, name):
        key = name.strip().lower()
        if key in self.area_cache:
            return self.area_cache[key]
        found = self.target.search("dvz.area", [["name", "=", name]], limit=1)
        area_id = found[0] if found else self.target.create("dvz.area", {"name": name})
        if not found:
            print(f"    [CREATE] area {name!r} -> id={area_id}")
        self.area_cache[key] = area_id
        return area_id

    def get_or_create_salesperson_employee(self, name):
        """hr.employee for the Sales field. A brand-new one is archived
        right away - a name from a historical tracking sheet isn't
        necessarily a real, currently-employed staff member. An
        employee that ALREADY exists (found by name) is left exactly
        as-is, active or not - this never archives someone who's
        genuinely on staff."""
        key = name.strip().lower()
        if key in self.employee_cache:
            return self.employee_cache[key]
        found = self.target.search(
            "hr.employee", [["name", "=", name]], limit=1, context={"active_test": False},
        )
        if found:
            employee_id = found[0]
        else:
            employee_id = self.target.create("hr.employee", {"name": name, "active": False})
            print(f"    [CREATE] employee {name!r} -> id={employee_id} (archived)")
        self.employee_cache[key] = employee_id
        return employee_id


# ============================================================================
# Lead creation
# ============================================================================

def import_row(target, matcher, row, apply_changes):
    quote = str(row["quote"]).strip() if row.get("quote") else None

    if quote:
        existing = target.search("crm.lead", [["po_ref", "=", quote]], limit=1)
        if existing:
            print(f"  [SKIP] Quote {quote!r}: already exists (id={existing[0]})")
            return None

    if not row.get("customer"):
        print(f"  [FAIL] Quote {quote!r}: no Customer given - skipped")
        return None

    label = quote or row["customer"]

    if not apply_changes:
        print(f"  [DRY-RUN] Would create lead for Quote {label!r} "
              f"(customer={row['customer']})")
        return None

    partner_id = matcher.get_or_create_partner(row["customer"])

    lead_vals = {
        "name": row.get("project") or row["customer"],
        "partner_id": partner_id,
        "po_ref": quote or False,
        "inquiry_date": row.get("date") or False,
        "expected_revenue": row.get("value") or 0.0,
        "remarks": row.get("remarks") or False,
        "type": "opportunity",
    }

    if row.get("project"):
        lead_vals["dvz_project"] = [(6, 0, [matcher.get_or_create_project(row["project"])])]
    if row.get("system"):
        lead_vals["system_ids"] = [(6, 0, [matcher.get_or_create_system(row["system"])])]
    if row.get("brand"):
        lead_vals["brand_ids"] = [(6, 0, [matcher.get_or_create_brand(row["brand"])])]
    if row.get("area"):
        lead_vals["area_ids"] = [(6, 0, [matcher.get_or_create_area(row["area"])])]
    if row.get("sales"):
        lead_vals["sales_ids"] = [(6, 0, [matcher.get_or_create_salesperson_employee(row["sales"])])]

    lead_id = target.create("crm.lead", lead_vals)

    status = (row.get("status") or "").strip().lower()
    if status == "won":
        won_stage = target.search("crm.stage", [["is_won", "=", True]], limit=1)
        if won_stage:
            target.write("crm.lead", [lead_id], {"stage_id": won_stage[0]})
        else:
            print(f"    [WARN] no CRM stage has is_won=True - lead {lead_id} "
                  f"left open, mark it Won manually.")
    elif status == "lost":
        target.execute("crm.lead", "action_set_lost", [lead_id])

    print(f"  [OK] Quote {label!r}: created as crm.lead id={lead_id}")
    return lead_id


# ============================================================================
# Main
# ============================================================================

def main():
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually create records in Odoo 19. Without this flag, "
             "the script only prints what it would do."
    )
    parser.add_argument(
        "--only", metavar="QUOTE", default=None,
        help="Only process a single row by exact Quote value."
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only process the first N rows (after --offset is applied)."
    )
    parser.add_argument(
        "--offset", type=int, default=0,
        help="Skip this many rows from the start of the file before "
             "applying --limit."
    )
    args = parser.parse_args()

    print(f"Mode: {'APPLY (will write to target)' if args.apply else 'DRY-RUN (no changes will be made)'}")

    rows = read_rows_from_excel(EXCEL_PATH, SHEET_NAME)
    print(f"Loaded {len(rows)} row(s) from {EXCEL_PATH}")

    if args.only:
        rows = [r for r in rows if str(r.get("quote") or "").strip() == args.only]
        if not rows:
            sys.exit(f"ERROR: --only {args.only!r} does not match any Quote in the file.")
    else:
        rows = rows[args.offset:]
        if args.limit is not None:
            rows = rows[:args.limit]
        print(f"Processing {len(rows)} row(s) after offset={args.offset}, limit={args.limit}.")

    try:
        target = OdooConnection(**TARGET, label="target/v19")
    except RuntimeError as e:
        sys.exit(f"ERROR: {e}")

    matcher = RecordMatcher(target)

    created = []
    failed = []
    for row in rows:
        try:
            lead_id = import_row(target, matcher, row, args.apply)
            if lead_id:
                created.append(lead_id)
        except Exception as e:
            label = row.get("quote") or row.get("customer") or "<unknown row>"
            failed.append(label)
            print(f"  [ERROR] {label!r}: {e} - skipped, continuing with next row")
            continue

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Created {len(created)} lead(s): {created}")
    if failed:
        print(f"Failed/skipped due to an error: {len(failed)} row(s):")
        for label in failed:
            print(f"    - {label}")
        print("Fix whatever caused these (bad data, a name that's too "
              "long, etc.) and re-run with --only <that Quote> to retry "
              "just those rows - everything else already created is "
              "safely skipped on re-run.")
    if not args.apply:
        print("This was a DRY RUN. Re-run with --apply to actually create records.")


if __name__ == "__main__":
    main()