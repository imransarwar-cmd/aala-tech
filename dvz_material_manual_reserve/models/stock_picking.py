from odoo import fields, models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    dvz_manual_project_id = fields.Many2one('project.project', string='Reservation Project', copy=False)
    dvz_manual_so_id = fields.Many2one('sale.order', string='Reference SO (Optional)', copy=False,
        help='Reference only; this transfer is independent of the SO delivery.')
