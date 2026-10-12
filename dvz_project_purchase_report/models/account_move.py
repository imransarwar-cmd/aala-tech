from odoo import api, fields, models

from ._helpers import project_share_percent


class AccountMove(models.Model):
    """Vendor bill: show only the part of each bill that belongs to one project.

    Same idea as the purchase order version: the amounts are computed on the fly,
    only for the bills on screen, from the analytic account passed in the
    context (dvz_analytic_account_id). Nothing is stored and no report tables
    or views are created.
    """
    _inherit = 'account.move'

    dvz_project_amount_untaxed = fields.Monetary(
        string='Project Amount (Untaxed)',
        currency_field='currency_id',
        compute='_compute_dvz_project_amount',
        readonly=True,
        help="This project's share of the bill, untaxed, in the bill's currency. "
             "Credit notes are negative.",
    )
    dvz_project_amount_company = fields.Monetary(
        string='Project Amount (Company Currency)',
        currency_field='company_currency_id',
        compute='_compute_dvz_project_amount',
        readonly=True,
        help="This project's share of the bill, untaxed, in company currency "
             "(as booked on the bill). Credit notes are negative.",
    )

    @api.depends_context('dvz_analytic_account_id')
    @api.depends('invoice_line_ids.price_subtotal', 'invoice_line_ids.balance',
                 'invoice_line_ids.analytic_distribution')
    def _compute_dvz_project_amount(self):
        analytic_id = self.env.context.get('dvz_analytic_account_id')
        for move in self:
            document_total = company_total = 0.0
            if analytic_id:
                is_refund = move.move_type in ('in_refund', 'out_refund')
                # Vendor documents: cost is the debit balance. Customer documents
                # (not used by the button, but kept correct): revenue is -balance.
                company_sign = 1.0 if move.move_type in ('in_invoice', 'in_refund') else -1.0
                for line in move.invoice_line_ids:
                    if line.display_type != 'product':
                        continue
                    percent = project_share_percent(analytic_id, line.analytic_distribution)
                    if not percent:
                        continue
                    document_total += (-1.0 if is_refund else 1.0) * line.price_subtotal * percent / 100.0
                    company_total += company_sign * line.balance * percent / 100.0
            move.dvz_project_amount_untaxed = document_total
            move.dvz_project_amount_company = company_total
