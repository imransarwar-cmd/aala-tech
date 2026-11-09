{
    'name': 'DVZ Honeywell Project Delivery Costing',
    'version': '19.0.1.0.0',
    'summary': 'Delivery-based project costing lines for selected Honeywell projects',
    'category': 'Projects/Accounting',
    'license': 'LGPL-3',
    'depends': [
        'dvz_project_purchase_report',
        'sale_stock',
        'stock_account',
        'analytic',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/project_delivery_cost_views.xml',
        'views/analytic_account_views.xml',
    ],
    'installable': True,
    'application': False,
}
