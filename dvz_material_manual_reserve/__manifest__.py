{
    'name': 'Manual Material Reservation Extension',
    'version': '19.0.1.0.0',
    'summary': 'Manual native-stock reservation, project and SO columns',
    'category': 'Inventory/Inventory',
    'license': 'LGPL-3',
    'depends': ['dvz_material_reservation_view', 'sale_stock', 'project'],
    'data': [
        'security/ir.model.access.csv',
        'views/reservation_view_extend.xml',
        'wizard/manual_reservation_views.xml',
    ],
    'installable': True,
    'application': False,
}
