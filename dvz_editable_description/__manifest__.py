# -*- coding: utf-8 -*-
{
    "name": "DVZ Editable Description After Confirmation",
    "version": "19.0.1.0.0",
    "summary": "Description stays editable on Sale Order lines, Deliveries, "
                "and Invoice lines at any state (confirmed, locked, "
                "validated, posted). Edits sync across all three "
                "automatically.",
    "author": "Genius Valley",
    "category": "Sales",
    "license": "OPL-1",
    "depends": [
        "sale_stock",
        "account",
    ],
    "data": [
        "views/sale_account_views.xml",
        "views/stock_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
