"""The report app (menus, SQL views, dashboard) was removed in 19.0.7.0.0.

Odoo drops the views of removed models itself, but doing it first, explicitly,
avoids any dependency problem while the old models are being removed.
"""

OLD_VIEWS = (
    'dvz_project_invoice_report',
    'dvz_project_invoice_line',
    'dvz_project_purchase_report',
    'dvz_project_purchase_line',
    'dvz_project_sale_report',
    'dvz_project_sale_line',
    'dvz_project_dashboard',
)


def migrate(cr, version):
    for view in OLD_VIEWS:
        cr.execute('DROP VIEW IF EXISTS %s CASCADE' % view)
