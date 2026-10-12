{
    'name': 'Project Reporting',
    'version': '19.0.6.0.2',
    'summary': 'Project sales, procurement and invoicing reports '
               '- no custom security groups or record rules',
    'category': 'Accounting/Reporting',
    'license': 'LGPL-3',
    'depends': ['sale', 'purchase', 'account', 'analytic'],
    'data': [
        'security/ir.model.access.csv',
        'views/project_purchase_views.xml',
        'views/project_sale_views.xml',
        'views/native_project_po_views.xml',
        'views/analytic_account_views.xml',
        'views/project_reporting_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
}
