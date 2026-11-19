{
    "name": "DVZ Manual Material Reservation",
    "version": "19.0.3.0.0",
    "summary": "Saved reservation requests with native transfers and a product report",
    "category": "Inventory/Inventory",
    "author": "DVZ",
    "license": "LGPL-3",
    "depends": ["sale_stock", "project", "mail"],
    "data": [
        "security/reservation_security.xml",
        "security/ir.model.access.csv",
        "data/reservation_sequence.xml",
        "views/reservation_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
