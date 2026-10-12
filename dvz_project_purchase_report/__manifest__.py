{
    'name': 'Project Amount Smart Buttons',
    'version': '19.0.7.0.0',
    'summary': 'On the analytic account: Project PO and Project Bill Amount buttons '
               'that show only the project\'s own share of each document',
    'category': 'Accounting/Reporting',
    'license': 'LGPL-3',
    'depends': ['purchase', 'account', 'analytic'],
    'data': [
        'views/native_project_po_views.xml',
        'views/native_project_bill_views.xml',
        'views/analytic_account_views.xml',
    ],
    'installable': True,
    'application': False,
}
