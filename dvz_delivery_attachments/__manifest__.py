{
    'name': 'Delivery Order Attachment Viewer',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'View direct delivery attachments from the delivery list',
    'depends': ['stock'],
    'data': ['wizard/delivery_attachment_wizard_views.xml', 'views/stock_picking_views.xml'],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
