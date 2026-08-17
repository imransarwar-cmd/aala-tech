# -*- coding: utf-8 -*-
{
    "name": "DVZ Sale Order Analytic Account",
    "version": "19.0.1.0.0",
    "summary": "Restores a single header-level Analytic Account field on Sale Orders/Quotations (like Odoo 16), propagating it to each order line's analytic distribution",
    "author": "Genius Valley.",
    "category": "Sales",
    "license": "OPL-1",
    "depends": [
        "sale",
        "analytic",
    ],
    "data": [
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
