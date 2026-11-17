{
    "name": "Sales Order Lock Control",
    "version": "19.0.1.2.0",
    "summary": "Strict closed-order protection with group-controlled reopening",
    "description": """
Closed sales orders and all their lines, including custom fields, are
read-only for every user. The assigned permission group can close/reopen
orders but must explicitly reopen before editing. No privileged-edit bypass. Displays Open / Closed as a form ribbon and a stored list
column immediately after the native order status, with
search filters and grouping. Uses Odoo's existing locked flag.
""",
    "author": "Digital Vizta",
    "category": "Sales/Sales",
    "license": "LGPL-3",
    "depends": ["sale_management"],
    "data": [
        "security/sale_lock_groups.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
