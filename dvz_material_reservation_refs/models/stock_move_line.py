from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    dvz_reservation_so_id = fields.Many2one(
        'sale.order', string='SO Number', compute='_compute_dvz_reservation_refs',
        compute_sudo=False,
    )
    dvz_reservation_project_id = fields.Many2one(
        'project.project', string='Project', compute='_compute_dvz_reservation_refs',
        compute_sudo=False,
    )

    @api.depends(
        'picking_id', 'picking_id.dvz_reservation_project_id',
        'picking_id.dvz_reservation_sale_id', 'picking_id.sale_id',
        'move_id.sale_line_id', 'move_id.sale_line_id.order_id',
    )
    def _compute_dvz_reservation_refs(self):
        for line in self:
            picking = line.picking_id
            order = (
                line.move_id.sale_line_id.order_id
                or picking.sale_id
                or picking.dvz_reservation_sale_id
            )
            line.dvz_reservation_so_id = order
            project = picking.dvz_reservation_project_id
            if not project and order:
                # Existing SO custom project selectors are optional: only use
                # an actual project.project relation, never a text-name match.
                for field_name in ('project_id', 'project_ids'):
                    fld = order._fields.get(field_name)
                    if fld and getattr(fld, 'comodel_name', None) == 'project.project':
                        projects = order[field_name]
                        if len(projects) == 1:
                            project = projects
                            break
            if not project and line.move_id.sale_line_id:
                so_line = line.move_id.sale_line_id
                fld = so_line._fields.get('project_id')
                if fld and getattr(fld, 'comodel_name', None) == 'project.project':
                    project = so_line.project_id
            line.dvz_reservation_project_id = project
