from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SystemMaster(models.Model):
    _inherit = 'system.master'

    dvz_department_id = fields.Many2one(
        'dvz.sale.division',
        string='Department',
        ondelete='restrict',
        index=True,
        help='Department that owns this system. Sales Orders only show systems belonging to the selected department.',
    )

    @api.constrains('dvz_department_id')
    def _check_department_active(self):
        for system in self:
            if system.dvz_department_id and not system.dvz_department_id.active:
                raise ValidationError(_('Select an active Department for the system.'))
