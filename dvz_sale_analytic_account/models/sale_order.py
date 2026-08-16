# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = "sale.order"

    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account",
        copy=False,
        help="Analytic account for this whole quotation/order, restoring the "
             "single header-level field from Odoo 16. Since Odoo 17+ tracks "
             "analytics per order line via analytic_distribution rather than "
             "one field per order, setting this propagates a 100% "
             "distribution to that account across every order line that "
             "doesn't already have its own distribution set.",
    )

    def _dvz_apply_analytic_account_to_lines(self, lines=None):
        """Push this order's analytic_account_id onto the given lines'
        analytic_distribution (100% to that single account). Only touches
        lines that don't already have a distribution, so it never silently
        overwrites analytics someone has deliberately set per line."""
        for order in self:
            if not order.analytic_account_id:
                continue
            target_lines = lines if lines is not None else order.order_line
            target_lines = target_lines.filtered(
                lambda l: l.order_id == order and not l.analytic_distribution and not l.display_type
            )
            if target_lines:
                distribution = {str(order.analytic_account_id.id): 100}
                target_lines.write({"analytic_distribution": distribution})

    @api.onchange("analytic_account_id")
    def _onchange_dvz_analytic_account_id(self):
        for order in self:
            if order.analytic_account_id:
                distribution = {str(order.analytic_account_id.id): 100}
                for line in order.order_line.filtered(lambda l: not l.display_type):
                    line.analytic_distribution = distribution

    def write(self, vals):
        res = super().write(vals)
        if "analytic_account_id" in vals:
            self._dvz_apply_analytic_account_to_lines()
        return res

    def action_confirm(self):
        res = super().action_confirm()
        self._dvz_apply_analytic_account_to_lines()
        return res


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            if (
                line.order_id.analytic_account_id
                and not line.analytic_distribution
                and not line.display_type
            ):
                line.analytic_distribution = {
                    str(line.order_id.analytic_account_id.id): 100
                }
        return lines
