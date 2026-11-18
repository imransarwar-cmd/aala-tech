from odoo import fields, models


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    dvz_benefit_rule = fields.Boolean(
        string='Employee Benefit Rule', copy=True,
        help='Identifies the native employee benefit rules and their payslip inputs.',
    )


class HrPayrollStructure(models.Model):
    _inherit = 'hr.payroll.structure'

    def _dvz_native_rules(self):
        self.ensure_one()
        pairs = self._get_parent_structure().get_all_rules()
        return self.env['hr.salary.rule'].browse(list(dict.fromkeys(rule_id for rule_id, sequence in pairs)))
