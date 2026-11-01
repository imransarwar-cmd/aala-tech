from odoo import api, fields, models
from odoo.exceptions import ValidationError
from ..naming import short_code


class ResUsers(models.Model):
    _inherit = 'res.users'

    dvz_sales_abbreviation = fields.Char(
        string='Salesperson Abbreviation', copy=False,
        help='Explicit project-naming code, for example AIB. Not inferred from the user name.'
    )

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for original in vals_list:
            vals = dict(original)
            if 'dvz_sales_abbreviation' in vals:
                try:
                    vals['dvz_sales_abbreviation'] = short_code(
                        vals['dvz_sales_abbreviation'], 'Salesperson abbreviation', required=False
                    ) or False
                except ValueError as exc:
                    raise ValidationError(str(exc)) from exc
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        vals = dict(vals)
        if 'dvz_sales_abbreviation' in vals:
            try:
                vals['dvz_sales_abbreviation'] = short_code(
                    vals['dvz_sales_abbreviation'], 'Salesperson abbreviation', required=False
                ) or False
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
        return super().write(vals)

    @api.constrains('dvz_sales_abbreviation')
    def _check_sales_abbreviation(self):
        for user in self:
            try:
                short_code(user.dvz_sales_abbreviation, 'Salesperson abbreviation', required=False)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
