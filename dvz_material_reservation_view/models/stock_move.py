from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    dvz_res_customer_id = fields.Many2one(
        'res.partner', string='Customer', compute='_compute_dvz_res_refs')
    dvz_res_so_id = fields.Many2one(
        'sale.order', string='SO Number', compute='_compute_dvz_res_refs')
    dvz_res_project_id = fields.Many2one(
        'project.project', string='Project', compute='_compute_dvz_res_refs')

    @api.depends('picking_id', 'sale_line_id', 'picking_id.partner_id')
    def _compute_dvz_res_refs(self):
        for move in self:
            picking = move.picking_id
            so = move.sale_line_id.order_id
            if not so and picking:
                so = picking.sale_id
            if not so and picking and 'dvz_manual_so_id' in picking._fields:
                so = picking.dvz_manual_so_id
            project = False
            if picking and 'dvz_manual_project_id' in picking._fields:
                project = picking.dvz_manual_project_id
            if not project and so:
                fld = so._fields.get('project_id')
                if fld and getattr(fld, 'comodel_name', None) == 'project.project':
                    project = so.project_id
            if not project and move.sale_line_id:
                line = move.sale_line_id
                fld = line._fields.get('project_id')
                if fld and getattr(fld, 'comodel_name', None) == 'project.project':
                    project = line.project_id
            move.dvz_res_customer_id = picking.partner_id or so.partner_id if picking or so else False
            move.dvz_res_so_id = so
            move.dvz_res_project_id = project
