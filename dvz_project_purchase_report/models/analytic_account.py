from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    dvz_budget = fields.Float(
        string='Estimated Budget',
        digits=(16, 2),
        help='Planned total COST for this project, in company currency. '
             'Used by Project Reporting to show budget used / remaining and '
             'the planned margin (agreed price minus this budget).',
    )

    # Display the EXACT native Odoo count, not the count from the wider PO-line report.
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

    def action_dvz_open_project_pnl(self):
        """Open this project's Profit & Loss summary (form if one row, else list)."""
        self.ensure_one()
        rows = self.env['dvz.project.dashboard'].search([('analytic_account_id', '=', self.id)])
        if not rows:
            raise UserError(_('Nothing has been booked to this project yet '
                              '(no sale orders, purchase orders, bills or invoices).'))
        action = self.env.ref('dvz_project_purchase_report.action_dvz_project_dashboard').read()[0]
        action['context'] = {}
        if len(rows) == 1:
            form = self.env.ref('dvz_project_purchase_report.view_dvz_project_dashboard_form')
            action.update({'res_id': rows.id, 'view_mode': 'form', 'views': [(form.id, 'form')]})
        else:
            action['domain'] = [('analytic_account_id', '=', self.id)]
        return action
