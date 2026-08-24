# -*- coding: utf-8 -*-
{
    "name": "DVZ Editable Description After Confirmation",
    "version": "19.0.1.0.0",
    "summary": "Allows editing the Description field on Sale Order lines, "
                "Invoice lines, and Down Payment invoice lines even after "
                "the order/invoice is confirmed, locked, or posted.",
    "author": "Genius Valley",
    "category": "Sales",
    "license": "OPL-1",
    "depends": [
        "sale",
        "account",
    ],
    "data": [
        "views/sale_account_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
