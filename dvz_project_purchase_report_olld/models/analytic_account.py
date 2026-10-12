from odoo import fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

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
