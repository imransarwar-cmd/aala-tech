"""Remove the stale act_window.view records from older versions.

They registered only a FORM view for each action, so Odoo opened the form
first (a blank "New" record) instead of the list. The actions now rely on
the default view order, so the leftovers must go.
"""
from odoo import SUPERUSER_ID, api

STALE = (
    'action_po_line_form_view',
    'action_vendor_bills_form_view',
    'action_customer_invoices_form_view',
    'action_invoice_lines_form_view',
    'action_dvz_project_dashboard_form_view',
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for name in STALE:
        record = env.ref('dvz_project_purchase_report.%s' % name, raise_if_not_found=False)
        if record and record._name == 'ir.actions.act_window.view':
            record.unlink()
