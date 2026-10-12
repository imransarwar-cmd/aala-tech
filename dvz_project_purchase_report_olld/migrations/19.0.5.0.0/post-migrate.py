"""Remove legacy project reporting access groups and record rules on upgrade."""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    module = 'dvz_project_purchase_report'
    rules = [
        'rule_dvz_project_purchase_report_company', 'rule_dvz_project_purchase_report_own', 'rule_dvz_project_purchase_report_all',
        'rule_dvz_project_purchase_line_company', 'rule_dvz_project_purchase_line_own', 'rule_dvz_project_purchase_line_all',
        'rule_dvz_project_invoice_line_company', 'rule_dvz_project_invoice_line_own', 'rule_dvz_project_invoice_line_all',
        'rule_dvz_project_invoice_report_company', 'rule_dvz_project_invoice_report_own', 'rule_dvz_project_invoice_report_all',
        'rule_dvz_dashboard_company',
    ]
    for xmlid in rules:
        record = env.ref('%s.%s' % (module, xmlid), raise_if_not_found=False)
        if record and record._name == 'ir.rule':
            record.unlink()
    for xmlid in ('group_project_purchase_all', 'group_project_purchase_own', 'group_project_finance_all', 'group_project_finance_own'):
        record = env.ref('%s.%s' % (module, xmlid), raise_if_not_found=False)
        if record and record._name == 'res.groups':
            record.unlink()
