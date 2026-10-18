from odoo import api, fields, models, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    delivery_attachment_count = fields.Integer(
        string='Documents', compute='_compute_delivery_attachment_count'
    )

    def _compute_delivery_attachment_count(self):
        pickings = self.filtered(lambda p: p.picking_type_code == 'outgoing')
        counts = {}
        if pickings:
            data = self.env['ir.attachment']._read_group(
                [('res_model', '=', 'stock.picking'), ('res_id', 'in', pickings.ids),
                 ('type', '=', 'binary')],
                ['res_id'], ['__count'],
            )
            counts = {res_id: count for res_id, count in data}
        for picking in self:
            picking.delivery_attachment_count = counts.get(picking.id, 0)

    def action_view_delivery_attachments(self):
        self.ensure_one()
        if self.picking_type_code != 'outgoing':
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delivery Documents'),
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'views': [(self.env.ref('dvz_delivery_attachments.view_delivery_attachment_list').id, 'list'),
                      (self.env.ref('dvz_delivery_attachments.view_delivery_attachment_form').id, 'form')],
            'target': 'new',
            'domain': [('res_model', '=', 'stock.picking'),
                       ('res_id', '=', self.id), ('type', '=', 'binary')],
            'context': {'create': False, 'edit': False, 'delete': False},
        }
