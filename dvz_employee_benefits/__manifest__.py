{
    'name': 'DVZ Employee Benefits and Allowances',
    'summary': 'Native salary structure, salary rules and payslip inputs for employee benefits',
    'version': '19.0.2.0.0',
    'category': 'Human Resources/Payroll',
    'author': 'DVZ',
    'license': 'LGPL-3',
    'depends': ['om_hr_payroll'],
    'data': [
        'data/salary_rules.xml',
        'data/salary_structure.xml',
        'views/hr_version_views.xml',
        'views/hr_salary_rule_views.xml',
    ],
    'installable': True,
    'application': False,
}
