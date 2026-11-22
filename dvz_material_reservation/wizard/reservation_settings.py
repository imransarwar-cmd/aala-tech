from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class ReservationSettings(models.TransientModel):
    _name = 'dvz.reservation.settings'
    _description = 'Material Reservation Settings (Current Company)'

    company_id = fields.Many2one('res.company', readonly=True, default=lambda self: self.env.company, required=True)
    automatic = fields.Boolean(string='Reserve available materials on SO confirmation', default=True)
    project_field_id = fields.Many2one('ir.model.fields', string='Existing SO Project / Analytic Field',
        domain="[('model', '=', 'sale.order'), ('ttype', '=', 'many2one'), ('relation', 'in', ['project.project', 'account.analytic.account'])]")
    project_reference_field_id = fields.Many2one(
        'ir.model.fields', string='Existing SO Project Reference (Text)',
        domain="[('model', '=', 'sale.order'), ('ttype', '=', 'char')]",
        help='Select the existing Sales Order Char field whose value should be copied to the reservation for reference.',
    )

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        company = self.env.company
        values.update(company_id=company.id,
                      automatic=company.dvz_auto_material_reservation,
                      project_field_id=company.dvz_reservation_project_field_id.id,
                      project_reference_field_id=company.dvz_reservation_project_reference_field_id.id)
        return values

    def action_save(self):
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('stock.group_stock_manager'):
            raise AccessError(_('Only Inventory Administrators can change reservation settings.'))
        if self.company_id != self.env.company:
            raise AccessError(_('Switch to the correct active company and reopen settings.'))
        # Explicit, narrow company settings write; no unrelated company fields.
        self.company_id.sudo().write({
            'dvz_auto_material_reservation': self.automatic,
            'dvz_reservation_project_field_id': self.project_field_id.id,
            'dvz_reservation_project_reference_field_id': self.project_reference_field_id.id,
        })
        return {'type': 'ir.actions.act_window_close'}
