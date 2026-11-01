from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from ..naming import short_code


class SaleDivision(models.Model):
    _name = 'dvz.sale.division'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Sales Division / Department'
    _order = 'sequence, code, name, id'
    _rec_names_search = ['code', 'name']
    _check_company_auto = True
    # Internal readers can discuss a visible division without gaining master-data write access.
    # Odoo still enforces ACLs, record rules and normal mail/activity permissions.
    _mail_post_access = 'read'

    name = fields.Char(string='Division / Department Name', required=True, tracking=True)
    code = fields.Char(string='Code', required=True, index=True, tracking=True,
                       help='For example EM. This code becomes the second part of the project name.')
    company_id = fields.Many2one('res.company', required=True,
                                default=lambda self: self.env.company, index=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)

    _code_company_unique = models.Constraint(
        'UNIQUE(company_id, code)', 'The division code must be unique within its company.'
    )

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for division in self:
            division.display_name = '[%s] %s' % (division.code or '', division.name or '')

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for original in vals_list:
            vals = dict(original)
            if 'code' in vals:
                try:
                    vals['code'] = short_code(vals['code'], 'Division code')
                except ValueError as exc:
                    raise ValidationError(str(exc)) from exc
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        vals = dict(vals)
        if 'code' in vals:
            try:
                vals['code'] = short_code(vals['code'], 'Division code')
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
        if 'company_id' in vals:
            # A division used in an order cannot silently move to a different company.
            for division in self.filtered(lambda d: d.company_id.id != vals['company_id']):
                if (self.env['sale.order'].sudo().with_context(active_test=False).search_count(
                        [('dvz_division_id', '=', division.id)], limit=1)
                        or self.env['project.project'].sudo().with_context(active_test=False).search_count(
                            [('dvz_division_id', '=', division.id)], limit=1)):
                    raise UserError(_('This division is in use. Create a separate division for the other company.'))
        return super().write(vals)

    @api.constrains('code')
    def _check_code(self):
        for division in self:
            try:
                short_code(division.code, 'Division code')
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
