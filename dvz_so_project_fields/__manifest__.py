# -*- coding: utf-8 -*-
{
    "name": "DVZ Sale Order Project Fields",
    "version": "19.0.1.0.0",
    "summary": "Adds Sales Engineer, Project, Area, Division, System, Brand, "
                "Value (untaxed), and Status fields to Quotations/Sale "
                "Orders, with a Settings toggle to show/hide the section.",
    "author": "Genius Valley",
    "category": "Sales",
    "license": "OPL-1",
    "depends": [
        "sale",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/dvz_sale_system_views.xml",
        "views/sale_order_views.xml",
        # "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
