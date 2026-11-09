from odoo import models


def _analytic_account_ids(distribution):
    ids = set()
    for key in (distribution or {}):
        for part in str(key).split(','):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
    return ids


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()

        # Only sync moves that really reached Done. If Odoo opens an immediate
        # transfer/backorder wizard, the moves are not yet done and nothing is
        # costed until the actual validation completes.
        done_moves = self.move_ids.filtered(
            lambda m: m.state == 'done'
            and m.sale_line_id
            and m.location_dest_id.usage == 'customer'
        )
        if not done_moves:
            return res

        account_ids = set()
        for move in done_moves:
            account_ids |= _analytic_account_ids(
                move.sale_line_id.analytic_distribution
            )

        accounts = self.env['account.analytic.account'].browse(list(account_ids)).exists()
        for account in accounts.filtered('dvz_honeywell_delivery_costing'):
            account._dvz_sync_delivery_cost_moves(done_moves)

        return res
