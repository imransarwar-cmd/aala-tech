{
    'name': 'DVZ Sales Order Layout',
    'version': '19.0.1.0.2',
    'summary': 'Sales Order list and form layout: Department, Analytic Code and order dates',
    'category': 'Sales/Sales',
    'author': 'DVZ',
    'license': 'LGPL-3',
    'depends': ['sale_management', 'account', 'analytic', 'dvz_sale_project_naming'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
