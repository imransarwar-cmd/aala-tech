from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    dvz_reservation_project_id = fields.Many2one(
        'project.project', string='Reservation Project', copy=False,
        help='Optional project reference for a manually created reservation.',
    )
    dvz_reservation_sale_id = fields.Many2one(
        'sale.order', string='Manual Reservation SO', copy=False,
        help='Optional informational reference only. This manual transfer is not the sale order delivery.',
    )
