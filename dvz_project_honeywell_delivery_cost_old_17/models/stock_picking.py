from odoo import models

from .analytic_account import _distribution_account_ids


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()

        done_moves = self.move_ids.filtered(
            lambda m: m.state == 'done'
            and m.sale_line_id
            and m.location_dest_id.usage == 'customer'
        )
        if not done_moves:
            return res

        analytic_ids = set()
        SaleOrder = self.env['sale.order']

        for move in done_moves:
            analytic_ids |= _distribution_account_ids(
                move.sale_line_id.analytic_distribution
            )

            order = move.sale_line_id.order_id
            for fname in ('analytic_account_id', 'account_analytic_id', 'analytic_id'):
                field = SaleOrder._fields.get(fname)
                if field and getattr(field, 'comodel_name', None) == 'account.analytic.account':
                    account = order[fname]
                    if account:
                        analytic_ids.add(account.id)

        if not analytic_ids:
            return res

        accounts = self.env['account.analytic.account'].browse(list(analytic_ids)).exists()
        for account in accounts.filtered('dvz_honeywell_delivery_costing'):
            account._dvz_sync_delivery_cost_moves(done_moves)

        return res
