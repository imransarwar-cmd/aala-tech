from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DvzManualReservationWizard(models.TransientModel):
    _name = 'dvz.material.manual.wizard'
    _description = 'Manual Reservation Wizard'

    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    project_id = fields.Many2one('project.project', string='Project (Optional)')
    sale_order_id = fields.Many2one('sale.order', string='SO Reference (Optional)')
    picking_type_id = fields.Many2one('stock.picking.type', required=True, string='Delivery Operation',
        domain="[('code','=','outgoing'),('company_id','in',[False,company_id])]")
    line_ids = fields.One2many('dvz.material.manual.line', 'wizard_id', string='Products')

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        if 'picking_type_id' in fields_list and not result.get('picking_type_id'):
            op = self.env['stock.picking.type'].search([
                ('code','=','outgoing'), ('company_id','in',[False, self.env.company.id])], limit=1)
            if op:
                result['picking_type_id'] = op.id
        return result

    def action_create_reservation(self):
        self.ensure_one()
        if not self.env.user.has_group('stock.group_stock_user'):
            raise UserError(_('Inventory permission is required.'))
        if not self.line_ids:
            raise UserError(_('Add at least one product.'))
        if self.picking_type_id.code != 'outgoing':
            raise UserError(_('Select a delivery operation.'))
        if self.picking_type_id.company_id and self.picking_type_id.company_id != self.company_id:
            raise UserError(_('Operation type has a different company.'))
        if self.sale_order_id and (self.sale_order_id.company_id != self.company_id or self.sale_order_id.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id):
            raise UserError(_('SO reference does not match the customer/company.'))
        if self.project_id and self.project_id.company_id and self.project_id.company_id != self.company_id:
            raise UserError(_('Project belongs to another company.'))
        source = self.picking_type_id.default_location_src_id or self.picking_type_id.warehouse_id.lot_stock_id
        dest = self.picking_type_id.default_location_dest_id or self.partner_id.property_stock_customer
        if not source or source.usage != 'internal' or not dest or dest.usage != 'customer':
            raise UserError(_('Choose an operation with internal source and customer destination locations.'))
        for line in self.line_ids:
            if not line.product_id.is_storable or line.quantity <= 0:
                raise UserError(_('Use tracked-in-inventory products with positive quantities.'))
            if line.product_id.tracking != 'none':
                raise UserError(_('For lot/serial-tracked products, use the native Delivery form to select specific lots.'))
        picking = self.env['stock.picking'].with_company(self.company_id).create({
            'partner_id': self.partner_id.id,
            'picking_type_id': self.picking_type_id.id,
            'location_id': source.id,
            'location_dest_id': dest.id,
            'origin': self.sale_order_id.name if self.sale_order_id else _('Manual Material Reservation'),
            'dvz_manual_project_id': self.project_id.id or False,
            'dvz_manual_so_id': self.sale_order_id.id or False,
            'company_id': self.company_id.id,
        })
        move_model = self.env['stock.move'].with_company(self.company_id)
        moves = move_model
        for line in self.line_ids:
            moves |= move_model.create({
                'name': line.product_id.display_name,
                'picking_id': picking.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'product_uom': line.product_id.uom_id.id,
                'location_id': source.id,
                'location_dest_id': dest.id,
                'company_id': self.company_id.id,
            })
        moves._action_confirm(merge=False)
        picking.action_assign()
        return {'type':'ir.actions.act_window', 'name':_('Reserved Transfer'),
                'res_model':'stock.picking', 'res_id':picking.id,
                'view_mode':'form', 'target':'current'}


class DvzManualReservationLine(models.TransientModel):
    _name = 'dvz.material.manual.line'
    _description = 'Manual Reservation Product'

    wizard_id = fields.Many2one('dvz.material.manual.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', required=True,
        domain="[('is_storable','=',True)]")
    quantity = fields.Float(required=True, default=1.0, digits='Product Unit')
