{
    'name': 'DVZ Internal Bank and Cash Transfers',
    'version': '19.0.1.0.0',
    'summary': 'Bank to bank, bank to cash, cash to bank and cash to cash transfers',
    'category': 'Accounting/Accounting',
    'license': 'LGPL-3',
    'depends': ['base_accounting_kit'],
    'data': ['security/ir.model.access.csv', 'views/internal_transfer_views.xml'],
    'installable': True,
    'application': False,
}
