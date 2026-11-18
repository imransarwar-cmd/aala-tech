from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError


class SaleSupplySourceWizard(models.TransientModel):
    _name = 'dvz.sale.supply.source.wizard'
    _description = 'Record Sales Product Source Split'

    sale_line_id = fields.Many2one('sale.order.line', required=True, readonly=True)
    order_id = fields.Many2one(related='sale_line_id.order_id', readonly=True, compute_sudo=False)
    product_id = fields.Many2one(related='sale_line_id.product_id', readonly=True, compute_sudo=False)
    company_id = fields.Many2one(related='sale_line_id.company_id', compute_sudo=False)
    product_uom_id = fields.Many2one(related='sale_line_id.product_uom_id', readonly=True, compute_sudo=False)
    ordered_qty = fields.Float(related='sale_line_id.product_uom_qty', readonly=True, compute_sudo=False)
    delivered_qty = fields.Float(related='sale_line_id.qty_delivered', readonly=True, compute_sudo=False)
    stock_qty = fields.Float(string='Supply from Existing Stock', required=True, digits='Product Unit')
    purchase_qty = fields.Float(string='Supply from Purchase', required=True, digits='Product Unit')
    stock_used_qty = fields.Float(string='Already Delivered from Stock', required=True, digits='Product Unit')
    purchase_used_qty = fields.Float(string='Already Delivered from Purchase', required=True, digits='Product Unit')
    purchase_line_ids = fields.Many2many('purchase.order.line', string='Supporting Purchase Lines')
    note = fields.Text(string='Source Evidence / Note', required=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        line_id = values.get('sale_line_id') or self.env.context.get('default_sale_line_id')
        if line_id:
            line = self.env['sale.order.line'].browse(line_id).exists()
            line._dvz_require_source_manager()
            line.check_access('read')
            if not line:
                raise UserError(_('The sales line is no longer available.'))
            defaults = {
                'stock_qty': line.dvz_manual_stock_qty if line.dvz_source_override else line.dvz_stock_qty,
                'purchase_qty': line.dvz_manual_purchase_qty if line.dvz_source_override else line.dvz_purchase_qty,
                'stock_used_qty': line.dvz_manual_stock_used_qty if line.dvz_source_override else line.dvz_stock_used_qty,
                'purchase_used_qty': line.dvz_manual_purchase_used_qty if line.dvz_source_override else line.dvz_purchase_used_qty,
                'note': line.dvz_source_note or '',
            }
            if line.dvz_source_purchase_line_ids.has_access('read'):
                defaults['purchase_line_ids'] = [Command.set(line.dvz_source_purchase_line_ids.ids)]
            values.update({key: value for key, value in defaults.items() if key in fields_list})
        return values

    def action_apply(self):
        self.ensure_one()
        self.sale_line_id._dvz_apply_source_split(
            stock_plan=self.stock_qty, purchase_plan=self.purchase_qty,
            stock_used=self.stock_used_qty, purchase_used=self.purchase_used_qty,
            note=self.note, purchase_lines=self.purchase_line_ids)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
