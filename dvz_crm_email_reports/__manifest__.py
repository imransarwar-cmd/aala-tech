# -*- coding: utf-8 -*-
{
    "name": "CRM Email Reports",
    "version": "19.0.1.0.0",
    "summary": "Scheduled Excel report emails for CRM leads, plus an "
                "on-demand download - by Team, by Salesperson, or a "
                "combined per-salesperson-sheet report for Head(s).",
    "description": """
CRM Email Reports
==================
Adds a "Report Schedules" configuration (CRM > Reporting > Report
Schedules) where you set up who receives an automatic Excel export of
leads, and how often:

- Teams (multi-select) and/or specific Salespersons (multi-select) -
  both can be set on the same schedule at once.
- Send to Head: one combined workbook with a SEPARATE SHEET per
  salesperson, emailed to whichever user(s) you mark as "Head
  Recipients".
- Salespersons (if set individually): each one gets emailed ONLY their
  own leads, as a plain single-sheet workbook.
- Date range: either every lead ("All Leads") or only leads whose
  Inquiry date falls within a specific From/To range.
- Frequency: how many times per day this schedule sends automatically
  (a shared cron checks every 30 minutes and only actually sends once
  enough time has passed for that schedule's own frequency).

The Excel layout matches the company's existing tracking-sheet format
(Quote, Date, Customer, Project, System, Brand, Area, Sales, Pre-Sales,
Value (w/o VAT), Status, Remarks, Quotation Deadline, Reason For Lost) -
PO - Ref # is deliberately NOT included as a column, since that field
is used to store "Quote" (see dvz_crm_ext) rather than a distinct PO
reference.

A "Download Excel" button on each schedule generates the same report
immediately/on demand, independent of the email/frequency settings.
    """,
    "author": "Genius Valley",
    "category": "CRM",
    "license": "OPL-1",
    "depends": ["crm", "mail", "dvz_crm_ext"],
    "data": [
        "security/ir.model.access.csv",
        "views/dvz_report_schedule_views.xml",
        "data/ir_cron_data.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
