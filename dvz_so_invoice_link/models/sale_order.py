from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dvz_linked_invoice_ids = fields.Many2many(
        'account.move',
        'dvz_sale_order_invoice_ref_rel',
        'order_id', 'move_id',
        string='DVZ Referenced Invoices',
        copy=False,
        help='Reference only. Does not modify invoice lines, sales lines or accounting.',
        groups='sales_team.group_sale_salesman',
    )

    @api.constrains('dvz_linked_invoice_ids', 'company_id', 'partner_id')
    def _check_dvz_linked_invoices(self):
        for order in self:
            for move in order.dvz_linked_invoice_ids:
                if move.move_type != 'out_invoice':
                    raise ValidationError(_('Only customer invoices can be referenced.'))
                if move.company_id != order.company_id:
                    raise ValidationError(_('Invoice and Sales Order must belong to the same company.'))
                if move.commercial_partner_id != order.partner_id.commercial_partner_id:
                    raise ValidationError(_('Invoice and Sales Order must have the same commercial customer.'))
                if move.currency_id != order.currency_id:
                    raise ValidationError(_('Invoice and Sales Order currencies must match.'))

    @api.depends('invoice_ids', 'dvz_linked_invoice_ids')
    def _compute_invoice_count(self):
        super()._compute_invoice_count()
        for order in self:
            order.invoice_count = len(order.invoice_ids | order.dvz_linked_invoice_ids)

    def action_view_invoice(self, invoices=False):
        self.ensure_one()
        # Leave the standard behavior completely untouched if no manual links exist.
        if not self.dvz_linked_invoice_ids:
            return super().action_view_invoice(invoices=invoices)
        all_invoices = self.invoice_ids | self.dvz_linked_invoice_ids
        # Build on the standard action so its permissions, context and labels are retained.
        action = super().action_view_invoice(invoices=all_invoices)
        action['domain'] = [('id', 'in', all_invoices.ids)]
        # Ensure the button opens the full list, even if the standard action
        # would normally open one invoice directly.
        action.pop('res_id', None)
        action['view_mode'] = 'list,form'
        action['views'] = [(False, 'list'), (False, 'form')]
        return action
