from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    dvz_origin_sale_id = fields.Many2one(
        'sale.order', string='Naming Source SO', readonly=True, copy=False,
        check_company=True, ondelete='set null', index=True, groups='base.group_user',
    )
    dvz_division_id = fields.Many2one(
        'dvz.sale.division', string='Department', readonly=True,
        copy=False, ondelete='restrict', check_company=True, groups='base.group_user',
    )
    dvz_project_code = fields.Char(string='Project Code', readonly=True, copy=False,
                                  groups='base.group_user')

    @api.model
    def _dvz_order_from_create_values(self, values):
        """Use explicit native links only. Never guess from free-text project names."""
        orders = self.env['sale.order']
        line_id = values.get('sale_line_id')
        if line_id:
            orders |= self.env['sale.order.line'].browse(line_id).exists().order_id
        order_id = values.get('reinvoiced_sale_order_id')
        if order_id:
            orders |= self.env['sale.order'].browse(order_id).exists()
        if len(orders) > 1:
            # Leave intentionally multi-order projects alone rather than guess an owner.
            return self.env['sale.order']
        return orders

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for original in vals_list:
            vals = dict(original)
            if not vals.get('is_template', self.env.context.get('default_is_template', False)):
                # Native defaults supplied through context must also be respected.
                link_values = dict(vals)
                for field in ('sale_line_id', 'reinvoiced_sale_order_id'):
                    if field not in link_values and self.env.context.get('default_' + field):
                        link_values[field] = self.env.context['default_' + field]
                order = self._dvz_order_from_create_values(link_values)
                if order:
                    naming = order._dvz_project_naming_values()
                    if naming:
                        vals.update(naming)
            prepared.append(vals)
        return super().create(prepared)

    def _dvz_apply_order_naming(self, order):
        order.ensure_one()
        values = order._dvz_project_naming_values()
        if not values:
            return
        for project in self:
            if project.is_template:
                continue
            if project.company_id and project.company_id != order.company_id:
                raise UserError(_('Cannot name a project from a sales order in another company.'))
            if project.dvz_origin_sale_id and project.dvz_origin_sale_id != order:
                raise UserError(_('This project already has a different naming source sales order.'))
            changes = {}
            for key, value in values.items():
                old = project[key].id if key.endswith('_id') else project[key]
                if old != value:
                    changes[key] = value
            if changes:
                project.write(changes)

    @api.constrains('company_id', 'dvz_division_id', 'dvz_origin_sale_id')
    def _dvz_check_naming_company(self):
        for project in self:
            if not project.dvz_origin_sale_id:
                continue
            order = project.dvz_origin_sale_id
            if project.company_id and project.company_id != order.company_id:
                raise ValidationError(_('The project and naming source SO must use the same company.'))
            if project.dvz_division_id and project.dvz_division_id.company_id != order.company_id:
                raise ValidationError(_('The division and naming source SO must use the same company.'))
