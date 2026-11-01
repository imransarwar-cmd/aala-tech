{
    'name': 'DigitalVizta Excel Attachment Preview',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Read-only Excel preview for Odoo attachments across the ERP',
    'license': 'LGPL-3',
    'depends': ['web', 'mail'],
    'external_dependencies': {'python': ['openpyxl', 'xlrd']},
    'assets': {'web.assets_backend': [
        'dvz_excel_preview/static/src/js/preview.js',
        'dvz_excel_preview/static/src/scss/preview.scss',
    ]},
    'installable': True,
    'application': False,
}
