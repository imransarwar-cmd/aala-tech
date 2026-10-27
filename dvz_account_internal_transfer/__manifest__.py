{
    'name': 'Internal Bank and Cash Transfers',
    'version': '19.0.1.2.1',
    'summary': 'Bank and cash transfers through an internal transfer bridge account',
    'category': 'Accounting/Accounting',
    'license': 'LGPL-3',
    'depends': ['base_accounting_kit', 'mail'],
    'data': [
        'data/sequence.xml',
        'security/ir.model.access.csv',
        'security/internal_transfer_security.xml',
        'views/internal_transfer_views.xml',
    ],
    'installable': True,
    'application': False,
}
