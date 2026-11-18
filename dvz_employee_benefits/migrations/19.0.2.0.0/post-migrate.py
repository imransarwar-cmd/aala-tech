"""Convert unused v1 generated native rules to the new native-input formulas.

The pre-migration refuses an upgrade if any v1 business data exists. This
step only handles rules created by the old setup wizard in an empty setup.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    data = env['ir.model.data'].search([
        ('module', '=', 'dvz_employee_benefits'), ('model', '=', 'hr.salary.rule'),
        ('name', '=like', 'salary_rule_dvz_%'),
    ])
    for xml_id in data:
        native = env['hr.salary.rule'].browse(xml_id.res_id).exists()
        if not native:
            continue
        old_formula = "result = contract._dvz_benefit_amount(payslip.dict, %r)" % native.code
        old_rules = env['hr.salary.rule'].search([
            ('code', '=', native.code), ('id', '!=', native.id),
            ('amount_python_compute', '=', old_formula),
        ])
        for rule in old_rules:
            rule.write({
                'dvz_benefit_rule': True,
                'category_id': native.category_id.id,
                'sequence': native.sequence,
                'condition_select': native.condition_select,
                'condition_python': native.condition_python,
                'amount_select': native.amount_select,
                'amount_python_compute': native.amount_python_compute,
                'note': native.note,
            })
            existing = set(rule.input_ids.mapped('code'))
            for item in native.input_ids:
                if item.code not in existing:
                    env['hr.rule.input'].create({'name': item.name, 'code': item.code, 'input_id': rule.id})
