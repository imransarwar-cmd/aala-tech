from odoo import _, api, fields, models

from ._helpers import project_share_percent


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    # ------------------------------------------------------------------
    # Purchase orders (unchanged)
    # ------------------------------------------------------------------
    # Display the EXACT native Odoo count, not the count from a wider report.
    dvz_project_purchase_count = fields.Integer(
        string='Project PO Amount', compute='_compute_dvz_project_purchase_count'
    )

    def _compute_dvz_project_purchase_count(self):
        for account in self:
            account.dvz_project_purchase_count = account.purchase_order_count

    def action_dvz_project_purchase_orders(self):
        self.ensure_one()
        # Reuse Odoo's own PO smart-button action and domain. This is the key to
        # keeping the displayed PO set consistent with the native button.
        action = self.action_view_purchase_orders()
        view = self.env.ref('dvz_project_purchase_report.view_dvz_native_project_po_list')
        action.update({
            'name': 'Project Purchase Orders - %s' % self.display_name,
            'view_mode': 'list,form',
            'views': [(view.id, 'list'), (False, 'form')],
            'view_id': False,
            'context': dict(self.env.context, dvz_analytic_account_id=self.id),
        })
        # Always show the list, even when native Odoo would open one PO directly.
        action.pop('res_id', None)
        return action

    # ------------------------------------------------------------------
    # Vendor bills (new) - same idea, amounts are only this project's share
    # ------------------------------------------------------------------
    dvz_currency_id = fields.Many2one(
        'res.currency', string='Project Currency', compute='_compute_dvz_currency_id')
    dvz_project_bill_amount = fields.Monetary(
        string='Project Bill Amount',
        currency_field='dvz_currency_id',
        compute='_compute_dvz_project_bill_amount',
        help='Posted vendor bills (credit notes subtract), only the part allocated '
             'to this project, untaxed, in company currency.',
    )

    @api.depends('company_id')
    def _compute_dvz_currency_id(self):
        for account in self:
            account.dvz_currency_id = (account.company_id or self.env.company).currency_id

    def _dvz_project_bill_lines(self, states=('draft', 'posted')):
        """Vendor bill / credit note product lines allocated to this account."""
        self.ensure_one()
        return self.env['account.move.line'].search([
            ('analytic_distribution', 'in', [self.id]),
            ('move_id.move_type', 'in', ('in_invoice', 'in_refund')),
            ('move_id.state', 'in', list(states)),
            ('display_type', '=', 'product'),
        ])

    def _compute_dvz_project_bill_amount(self):
        for account in self:
            total = 0.0
            if account.id:
                for line in account._dvz_project_bill_lines(states=('posted',)):
                    total += line.balance * project_share_percent(
                        account.id, line.analytic_distribution) / 100.0
            account.dvz_project_bill_amount = total

    def action_dvz_project_vendor_bills(self):
        self.ensure_one()
        bills = self._dvz_project_bill_lines().move_id
        list_view = self.env.ref('dvz_project_purchase_report.view_dvz_native_project_bill_list')
        search_view = self.env.ref('dvz_project_purchase_report.view_dvz_native_project_bill_search')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Project Vendor Bills - %s') % self.display_name,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [(list_view.id, 'list'), (False, 'form')],
            'search_view_id': [search_view.id, search_view.name],
            'domain': [('id', 'in', bills.ids)],
            'context': {
                'create': False,
                'default_move_type': 'in_invoice',
                'dvz_analytic_account_id': self.id,
            },
        }
