from odoo import fields, models


class DvzProjectDeliveryCostLine(models.Model):
    _name = 'dvz.project.delivery.cost.line'
    _description = 'Project Delivery Cost Line'
    _order = 'delivery_date desc, id desc'
    _rec_name = 'product_id'

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )
    stock_move_id = fields.Many2one(
        'stock.move',
        string='Stock Move',
        required=True,
        ondelete='cascade',
        index=True,
    )
    picking_id = fields.Many2one(
        'stock.picking', string='Delivery', required=True, ondelete='cascade', index=True,
    )
    sale_order_id = fields.Many2one('sale.order', string='Sales Order', index=True)
    sale_line_id = fields.Many2one('sale.order.line', string='Sales Order Line', index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, index=True)
    product_uom_id = fields.Many2one('uom.uom', string='UoM', required=True)
    delivered_qty = fields.Float(string='Delivered Qty', digits='Product Unit of Measure')
    analytic_percent = fields.Float(string='Project %', digits=(16, 2), default=100.0)
    unit_cost = fields.Monetary(string='Unit Cost', currency_field='currency_id')
    amount = fields.Monetary(string='Delivered Cost', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, index=True)
    delivery_date = fields.Datetime(string='Delivery Date', index=True)

    _sql_constraints = [
        (
            'dvz_project_delivery_move_unique',
            'unique(analytic_account_id, stock_move_id)',
            'A delivery costing line already exists for this project and stock move.',
        ),
    ]
