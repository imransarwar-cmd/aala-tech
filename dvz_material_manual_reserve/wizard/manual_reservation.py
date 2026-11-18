from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DvzManualReservation(models.TransientModel):
    _name = 'dvz.manual.reservation'
    _description = 'Reserve Stock with Native Delivery Operation'

    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    picking_type_id = fields.Many2one(
        'stock.picking.type', string='Delivery Operation', required=True,
        domain="[('code', '=', 'outgoing'), ('company_id', 'in', [False, company_id])]",
    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    project_id = fields.Many2one('project.project', string='Project (Optional)')
    sale_order_id = fields.Many2one('sale.order', string='SO Number (Optional)',
                                   help='Reference only; a separate manual transfer will be created.')
    line_ids = fields.One2many('dvz.manual.reservation.line', 'wizard_id', string='Materials')

    @api.model
    def default_get(self, fields_list):
        data = super().default_get(fields_list)
        if 'picking_type_id' in fields_list and not data.get('picking_type_id'):
            operation = self.env['stock.picking.type'].search([
                ('code', '=', 'outgoing'),
                ('company_id', 'in', [False, self.env.company.id]),
            ], limit=1)
            if operation:
                data['picking_type_id'] = operation.id
        return data

    def action_reserve(self):
        self.ensure_one()
        if not self.env.user.has_group('stock.group_stock_user'):
            raise UserError(_('Only inventory users may create manual reservations.'))
        if self.picking_type_id.code != 'outgoing':
            raise ValidationError(_('Select an outgoing Delivery Operation.'))
        if self.picking_type_id.company_id and self.picking_type_id.company_id != self.company_id:
            raise ValidationError(_('The delivery operation belongs to another company.'))
        if self.sale_order_id and (
            self.sale_order_id.partner_id.commercial_partner_id
            != self.partner_id.commercial_partner_id
        ):
            raise ValidationError(_('The selected Sales Order belongs to another customer.'))
        if self.sale_order_id and self.sale_order_id.company_id != self.company_id:
            raise ValidationError(_('The Sales Order belongs to another company.'))
        if self.project_id and self.project_id.company_id and self.project_id.company_id != self.company_id:
            raise ValidationError(_('The project belongs to another company.'))
        if not self.line_ids:
            raise ValidationError(_('Add at least one product.'))

        source = self.picking_type_id.default_location_src_id or self.picking_type_id.warehouse_id.lot_stock_id
        destination = (
            self.picking_type_id.default_location_dest_id
            or self.partner_id.property_stock_customer
            or self.env.ref('stock.stock_location_customers')
        )
        if not source or source.usage != 'internal' or destination.usage != 'customer':
            raise ValidationError(_('A valid internal source and customer destination are required.'))

        for line in self.line_ids:
            if not line.product_id.is_storable:
                raise ValidationError(_('%s is not a stock-tracked product.') % line.product_id.display_name)
            if line.quantity <= 0:
                raise ValidationError(_('Reservation quantity must be greater than zero.'))
            if line.product_id.tracking != 'none':
                raise UserError(_(
                    'Tracked product %s requires lot/serial selection. Use the native Delivery Order '
                    'detailed operations to make this reservation.'
                ) % line.product_id.display_name)

        picking = self.env['stock.picking'].with_company(self.company_id).create({
            'partner_id': self.partner_id.id,
            'picking_type_id': self.picking_type_id.id,
            'location_id': source.id,
            'location_dest_id': destination.id,
            'origin': self.sale_order_id.name if self.sale_order_id else _('Manual Reservation'),
            'dvz_reservation_project_id': self.project_id.id or False,
            'dvz_reservation_sale_id': self.sale_order_id.id or False,
        })
        moves = self.env['stock.move'].with_company(self.company_id)
        for line in self.line_ids:
            moves |= moves.create({
                'name': line.product_id.display_name,
                'picking_id': picking.id,
                'picking_type_id': picking.picking_type_id.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'product_uom': line.product_id.uom_id.id,
                'location_id': source.id,
                'location_dest_id': destination.id,
                'company_id': self.company_id.id,
            })
        moves._action_confirm()
        # Reuse the normal Odoo stock reservation flow; do not adjust quants.
        picking.action_assign()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manual Reservation Transfer'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }


class DvzManualReservationLine(models.TransientModel):
    _name = 'dvz.manual.reservation.line'
    _description = 'Manual Reservation Product Line'

    wizard_id = fields.Many2one('dvz.manual.reservation', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True,
                                 domain="[('is_storable', '=', True)]")
    quantity = fields.Float(string='Quantity', required=True, default=1.0, digits='Product Unit of Measure')
