# -*- coding: utf-8 -*-
{
    "name": "Sale Order Report Fields",
    "version": "19.0.1.0.0",
    "summary": "Adds Sales Engineer, Customer Name, Area, Status, and Year to "
                "Sale Orders, links the existing Division and Brand master "
                "data (from aala_rest_api) to Sale Orders, and exposes all "
                "of these plus the existing System/Project fields as "
                "optional show/hide columns in the Quotations/Sale Orders "
                "list view.",
    "author": "Genius Valley",
    "category": "Sales",
    "license": "OPL-1",
    "depends": [
        "sale",
        "aala_rest_api",
        "hr",
    ],
    "data": [
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
