# -*- coding: utf-8 -*-
{
    "name": "CRM Project Lines",
    "version": "19.0.1.2.0",
    "summary": "Adds Project/Status to CRM Leads, plus a one2many line table "
                "(System, Activity, Sales, Presales, Inquiry, Due Date, "
                "Est. Closing) matching the tracking spreadsheet format. "
                "Auto-fills the matching Sale Order fields (from "
                "dvz_sale_report_fields) when a Quotation is created from "
                "an Opportunity. Customer field is now restricted to real "
                "customers, Presales auto-mirrors the Salesperson, a "
                "Customer's Contact field (scoped to the customer's own "
                "company) auto-fills Email/Phone, the line table's costing "
                "matches the company's Excel quotation sheet exactly "
                "(List Price / Discount / Freight & Custom / Exchange Rate "
                "-> Unit Cost, Profit% -> Unit Price), and a 'Print "
                "Quotation' button produces a PDF laid out the same way "
                "as that Excel sheet.",
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
        "data/dvz_brand_area_data.xml",
        "views/dvz_master_data_views.xml",
        "report/crm_lead_quotation_report.xml",
        "views/crm_lead_views.xml",
        "views/dvz_sale_order_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
