import math

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


ALLOWANCE_FIELDS = (
    'dvz_fuel_allowance', 'dvz_accommodation_allowance', 'dvz_travel_allowance',
    'dvz_mobile_allowance', 'dvz_meal_allowance', 'dvz_special_duty_allowance',
    'dvz_car_maintenance_allowance', 'dvz_medical_allowance', 'dvz_air_ticket_allowance',
)
PARAMETER_FIELDS = (
    'dvz_custom_salary_base', 'dvz_salary_days_divisor', 'dvz_hours_per_day',
    'dvz_ot_multiplier', 'dvz_pf_custom_base', 'dvz_pf_employee_rate',
    'dvz_pf_employer_rate', 'dvz_pf_employee_cap', 'dvz_pf_employer_cap',
)
HR_MANAGER = 'hr.group_hr_manager'


class HrVersion(models.Model):
    _inherit = 'hr.version'

    dvz_fuel_allowance = fields.Monetary(string='Fuel Allowance', groups=HR_MANAGER)
    dvz_accommodation_allowance = fields.Monetary(string='Accommodation Allowance', groups=HR_MANAGER)
    dvz_travel_allowance = fields.Monetary(string='Travel Allowance', groups=HR_MANAGER)
    dvz_mobile_allowance = fields.Monetary(string='Mobile / Telephone Allowance', groups=HR_MANAGER)
    dvz_meal_allowance = fields.Monetary(string='Meal / Food Allowance', groups=HR_MANAGER)
    dvz_special_duty_allowance = fields.Monetary(string='Special Duty Allowance', groups=HR_MANAGER)
    dvz_car_maintenance_allowance = fields.Monetary(string='Car Maintenance Allowance', groups=HR_MANAGER)
    dvz_medical_allowance = fields.Monetary(string='Medical Allowance', groups=HR_MANAGER)
    dvz_air_ticket_allowance = fields.Monetary(string='Air Ticket Allowance', groups=HR_MANAGER)

    dvz_salary_base = fields.Selection([
        ('wage', 'Employment Version Wage'), ('custom', 'Custom Salary Base'),
    ], required=True, default='wage', groups=HR_MANAGER,
        help='Base for leave encashment days, overtime hours and notice-period days.')
    dvz_custom_salary_base = fields.Monetary(string='Custom Daily / Hourly Salary Base', groups=HR_MANAGER)
    dvz_salary_days_divisor = fields.Float(string='Salary Days Divisor', digits=(16, 4), groups=HR_MANAGER,
        help='Enter the divisor specified by your payroll policy. Required for days or hours inputs.')
    dvz_hours_per_day = fields.Float(string='Salary Hours per Day', digits=(16, 4), groups=HR_MANAGER)
    dvz_ot_multiplier = fields.Float(string='Overtime Multiplier', digits=(16, 4), groups=HR_MANAGER,
        help='Enter the approved policy multiplier; no rate is assumed.')

    dvz_pf_enabled = fields.Boolean(string='Provident Fund Eligible', groups=HR_MANAGER)
    dvz_pf_base = fields.Selection([
        ('wage', 'Employment Version Wage'), ('custom', 'Custom PF Base'),
    ], required=True, default='wage', groups=HR_MANAGER)
    dvz_pf_custom_base = fields.Monetary(string='Custom PF Base', groups=HR_MANAGER)
    dvz_pf_employee_rate = fields.Float(string='Employee PF (%)', digits=(16, 4), groups=HR_MANAGER)
    dvz_pf_employer_rate = fields.Float(string='Employer PF (%)', digits=(16, 4), groups=HR_MANAGER)
    dvz_pf_employee_cap = fields.Monetary(string='Employee PF Cap', groups=HR_MANAGER,
        help='Zero means no cap on the contribution per payslip.')
    dvz_pf_employer_cap = fields.Monetary(string='Employer PF Cap', groups=HR_MANAGER,
        help='Zero means no cap on the contribution per payslip.')

    @api.constrains(*(ALLOWANCE_FIELDS + PARAMETER_FIELDS))
    def _check_dvz_amounts(self):
        for version in self:
            for field_name in ALLOWANCE_FIELDS + PARAMETER_FIELDS:
                value = version[field_name]
                if not math.isfinite(value) or value < 0:
                    raise ValidationError(_('%s must be a finite nonnegative value.') % version._fields[field_name].string)
            if version.dvz_pf_employee_rate > 100 or version.dvz_pf_employer_rate > 100:
                raise ValidationError(_('PF percentages must be between 0 and 100.'))
