from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dvz_auto_reserve_stock = fields.Boolean(
        string='Auto Reserve Material on Confirmation', default=True,
        help='When confirming this SO, reserve available stock using the native Odoo inventory engine.')

    def action_confirm(self):
        result = super().action_confirm()
        for order in self.filtered(lambda o: o.dvz_auto_reserve_stock and o.state == 'sale'):
            # Only existing SO pickings: no duplicate delivery or demand is created.
            pickings = order.picking_ids.filtered(
                lambda p: p.picking_type_id.code == 'outgoing' and p.state not in ('cancel','done'))
            for picking in pickings:
                # Using Odoo's standard reservation API rather than writing stock.move.line.
                if picking.move_ids.filtered(lambda m: m.state in ('confirmed','partially_available','assigned')):
                    picking.action_assign()
        return result
