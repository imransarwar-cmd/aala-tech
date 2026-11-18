{
    'name': 'DVZ Project Delivery Costing',
    'version': '19.0.1.9.0',
    'summary': 'Delivered value from analytic-linked SO lines: SO unit price x completed customer delivery quantity',
    'category': 'Projects/Accounting',
    'license': 'LGPL-3',
    'depends': [
        'base_setup',
        'project',
        'dvz_project_purchase_report',
        'sale_stock',
        'stock_account',
        'analytic',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/project_delivery_cost_views.xml',
        'views/analytic_account_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    # 'pre_init_hook': 'pre_init_hook',
}
