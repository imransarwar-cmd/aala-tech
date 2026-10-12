from odoo import api, fields, models

from ._helpers import project_share_percent


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    dvz_project_amount_untaxed = fields.Monetary(
        string='Project Amount (Untaxed)',
        currency_field='currency_id',
        compute='_compute_dvz_project_amount_untaxed',
        readonly=True,
    )

    @api.depends_context('dvz_analytic_account_id')
    @api.depends('order_line.price_subtotal', 'order_line.analytic_distribution')
    def _compute_dvz_project_amount_untaxed(self):
        analytic_id = self.env.context.get('dvz_analytic_account_id')
        for order in self:
            total = 0.0
            if analytic_id:
                for line in order.order_line:
                    if line.display_type:
                        continue
                    total += line.price_subtotal * project_share_percent(
                        analytic_id, line.analytic_distribution) / 100.0
            order.dvz_project_amount_untaxed = total
