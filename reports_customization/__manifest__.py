# -*- coding: utf-8 -*-

{
    "name": "Report Customization",
    "version": "19.0.1.0.0",
    "depends": [
        'base', 'web', 'purchase','stock',
    ],
    "author": "Ahmad Inayat",
    "category": "Accounting",
    "website": "https://genius-valley.com/",
    "support": "odoo@gvitt.com",
    # "images": ["static/description/assets/main_screenshot.gif","static/description/assets/main_screenshot.png", "static/description/assets/ghits_desktop_inv.jpg",
    #            "static/description/assets/ghits_labtop1.jpg"],
    "price": "0",
    "license": "OPL-1",
    "currency": "USD",
    "summary": "Report Customization",
    "description": """ Report Customization """ ,
    "data": [
        "view/report_view.xml",
        "view/report_views.xml",
        "view/product_views.xml",
        # "report/account_move.xml",
        # "view/account_move_views.xml"

    ],
    "installable": True,
    "auto_install": False,
    "application": True,
    'assets': {
        'web.report_assets_common': [
            'einv_sa/static/css/report_style.css',
        ],
    },
}
