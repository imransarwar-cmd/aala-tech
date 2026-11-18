from collections import Counter
import math

from odoo import api, models, _
from odoo.exceptions import ValidationError


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _dvz_input_amount(self, code, version_id):
        """Read native Other Inputs, preserving contract/version separation.

        Salary-rule Python contains the actual calculation; this helper only
        reads amounts. It does not introduce another benefit registry/model.
        """
        self.ensure_one()
        values = self.input_line_ids.filtered(
            lambda line: line.code == code and line.version_id.id == version_id
        ).mapped('amount')
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValidationError(_('Input %s must contain finite nonnegative amounts or quantities.') % code)
        total = sum(values)
        if not math.isfinite(total):
            raise ValidationError(_('The total for input %s is too large.') % code)
        return total

    @api.model
    def get_inputs(self, versions, date_from, date_to):
        result = super().get_inputs(versions, date_from, date_to)
        existing = {(row['version_id'], row['code']) for row in result}
        # OM's default get_inputs reads direct structure rules only. Include
        # benefit input definitions inherited through parent structures too.
        for version in versions:
            if not version.struct_id:
                continue
            definitions = version.struct_id._dvz_native_rules().filtered('dvz_benefit_rule').mapped('input_ids')
            for definition in definitions:
                key = (version.id, definition.code)
                if key not in existing:
                    result.append({'name': definition.name, 'code': definition.code, 'version_id': version.id})
                    existing.add(key)
        return result

    def _dvz_ensure_native_inputs(self, rules):
        self.ensure_one()
        existing = {(row.version_id.id, row.code) for row in self.input_line_ids}
        values = []
        for definition in rules.filtered('dvz_benefit_rule').mapped('input_ids'):
            key = (self.version_id.id, definition.code)
            if key not in existing:
                values.append({
                    'payslip_id': self.id, 'version_id': self.version_id.id,
                    'name': definition.name, 'code': definition.code, 'amount': 0.0,
                })
                existing.add(key)
        if values:
            self.env['hr.payslip.input'].create(values)

    def _dvz_validate_native_inputs(self, rules):
        self.ensure_one()
        version = self.version_id
        if not version:
            raise ValidationError(_('Select an employment version before computing these benefit rules.'))
        if (version.employee_id != self.employee_id or version.company_id != self.company_id
                or self.employee_id.company_id != self.company_id):
            raise ValidationError(_('Payslip, employee and employment version must have the same company.'))
        if self.company_id not in self.env.companies:
            raise ValidationError(_('Enable the payslip company in your company selector.'))
        counts = Counter(rules.mapped('code'))
        duplicate_codes = [code for code, count in counts.items() if count > 1]
        if duplicate_codes:
            raise ValidationError(_('Each salary rule code must appear once in the structure and its parents. Duplicates: %s') % ', '.join(sorted(duplicate_codes)))

        codes = set(rules.filtered('dvz_benefit_rule').mapped('code'))
        for line in self.input_line_ids.filtered(lambda row: row.code.startswith('DVZ_')):
            if line.version_id != version:
                raise ValidationError(_('Benefit input %s belongs to another employment version.') % line.code)
            self._dvz_input_amount(line.code, version.id)

        day_codes = []
        if 'DVZ_LEAVE_ENCASH' in codes:
            day_codes.append('DVZ_LEAVE_DAYS')
        if 'DVZ_NOTICE' in codes:
            day_codes.append('DVZ_NOTICE_DAYS')
        has_days = any(self._dvz_input_amount(code, version.id) for code in day_codes)
        has_hours = 'DVZ_OT' in codes and self._dvz_input_amount('DVZ_OT_HOURS', version.id)
        if has_days or has_hours:
            base = version.wage if version.dvz_salary_base == 'wage' else version.dvz_custom_salary_base
            if not math.isfinite(base) or base <= 0 or version.dvz_salary_days_divisor <= 0:
                raise ValidationError(_('Set a positive salary base and Salary Days Divisor for days/hours calculations.'))
        if has_hours and (version.dvz_hours_per_day <= 0 or version.dvz_ot_multiplier <= 0):
            raise ValidationError(_('Set positive Salary Hours per Day and Overtime Multiplier before paying OT hours.'))
        pf_rules = codes & {'DVZ_PF_EMPLOYEE', 'DVZ_PF_EMPLOYER'}
        if pf_rules and version.dvz_pf_enabled:
            rates = []
            if 'DVZ_PF_EMPLOYEE' in pf_rules:
                rates.append(version.dvz_pf_employee_rate)
            if 'DVZ_PF_EMPLOYER' in pf_rules:
                rates.append(version.dvz_pf_employer_rate)
            if any(rates):
                base = version.wage if version.dvz_pf_base == 'wage' else version.dvz_pf_custom_base
                if not math.isfinite(base) or base <= 0:
                    raise ValidationError(_('Set a positive PF salary base before calculating PF contributions.'))

        # Known duplicate recurring allowances from the dependency. Additional
        # cash inputs remain possible; the same recurring amount must not be
        # paid from both old and new contract fields.
        for new_code, new_field, old_code, old_field in (
            ('DVZ_ACCOMMODATION', 'dvz_accommodation_allowance', 'HRA', 'hra'),
            ('DVZ_TRAVEL', 'dvz_travel_allowance', 'Travel', 'travel_allowance'),
            ('DVZ_MEAL', 'dvz_meal_allowance', 'Meal', 'meal_allowance'),
            ('DVZ_MEDICAL', 'dvz_medical_allowance', 'Medical', 'medical_allowance'),
        ):
            if new_code in codes and old_code in counts and version[new_field] and version[old_field]:
                raise ValidationError(_('The %s allowance is entered in both the legacy field and the DVZ field. Keep one recurring amount.') % new_code)

        gross = rules.filtered(lambda rule: rule.code == 'GROSS')
        net = rules.filtered(lambda rule: rule.code == 'NET')
        for rule in rules.filtered('dvz_benefit_rule'):
            if rule.code == 'DVZ_PF_EMPLOYER':
                category = rule.category_id
                seen = set()
                while category:
                    if category.id in seen or category.code in ('BASIC', 'ALW', 'DED', 'GROSS', 'NET'):
                        raise ValidationError(_('Employer PF must use a separate employer-contribution category outside employee gross/net categories.'))
                    seen.add(category.id)
                    category = category.parent_id
            elif rule.code == 'DVZ_PF_EMPLOYEE':
                if net and rule.sequence >= net.sequence:
                    raise ValidationError(_('Employee PF must be calculated before Net Salary.'))
            elif gross and rule.sequence >= gross.sequence:
                raise ValidationError(_('Benefit earnings must be calculated before Gross Salary.'))
        return True

    def compute_sheet(self):
        for slip in self:
            structure = slip.struct_id or slip.version_id.struct_id
            rules = structure._dvz_native_rules() if structure else self.env['hr.salary.rule']
            if rules.filtered('dvz_benefit_rule'):
                slip._dvz_validate_native_inputs(rules)
                slip._dvz_ensure_native_inputs(rules)
            super(HrPayslip, slip.with_company(slip.company_id or self.env.company)).compute_sheet()
        return True
