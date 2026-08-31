# -*- coding: utf-8 -*-
{
    "name": "DVZ CRM Project Lines",
    "version": "19.0.1.0.0",
    "summary": "Adds Project/Status to CRM Leads, plus a one2many line table "
                "(System, Activity, Sales, Presales, Inquiry, Due Date, "
                "Est. Closing) matching the tracking spreadsheet format. "
                "Auto-fills the matching Sale Order fields (from "
                "dvz_sale_report_fields) when a Quotation is created from "
                "an Opportunity.",
    "author": "Genius Valley",
    "category": "CRM",
    "license": "OPL-1",
    "depends": [
        "crm",
        "sale_crm",
        "project",
        "aala_rest_api",
        "dvz_sale_report_fields",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/crm_lead_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
