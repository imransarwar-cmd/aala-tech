from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    dvz_auto_material_reservation = fields.Boolean(
        string='Reserve materials on SO confirmation', default=True,
        help='Attach the SO stock moves to a reservation and reserve available stock. '
             'Existing orders are not changed merely by installing the addon.')
    dvz_reservation_project_field_id = fields.Many2one(
        'ir.model.fields', string='Existing SO Project / Analytic Field',
        ondelete='set null',
        domain="[('model', '=', 'sale.order'), ('ttype', '=', 'many2one'), "
               "('relation', 'in', ['project.project', 'account.analytic.account'])]",
        help='Optional exact existing SO field. The addon adds no duplicate project field on the SO.')

    @api.constrains('dvz_reservation_project_field_id')
    def _check_dvz_project_field(self):
        for company in self:
            field = company.dvz_reservation_project_field_id
            if field and (field.model != 'sale.order' or field.ttype != 'many2one'
                          or field.relation not in ('project.project', 'account.analytic.account')):
                raise ValidationError(_('Select an existing Sales Order Many2one project or analytic account field.'))
