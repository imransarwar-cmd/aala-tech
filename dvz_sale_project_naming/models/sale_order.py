from copy import deepcopy
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from ..naming import make_project_code, make_project_name, reference, short_code
from ..layout import regroup_project_fields

_logger = logging.getLogger(__name__)

NAMING_INPUTS = {
    'dvz_division_id', 'dvz_project_reference', 'dvz_project_suffix', 'dvz_include_so_number',
}
SNAPSHOT_FIELDS = {'dvz_confirmed_project_code', 'dvz_confirmed_project_name'}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Reuse the existing System field from aala_rest_api; only constrain its choices.
    system = fields.Many2one(
        'system.master',
        string='System',
        domain="[('dvz_department_id', '=', dvz_division_id)]",
        tracking=True,

    )

    dvz_division_id = fields.Many2one(
        'dvz.sale.division', string='Department', check_company=True,
        ondelete='restrict', tracking=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
        help='Select the division used in this order project code, for example EM.'
    )
    dvz_salesperson_abbreviation = fields.Char(
        related='user_id.dvz_sales_abbreviation', string='Salesperson Abbreviation', readonly=True
    )
    dvz_project_reference = fields.Char(
        string='Project Reference', copy=False, tracking=True,
        help='Your business reference, for example 4128. Entered manually; not the SO sequence.'
    )
    dvz_project_suffix = fields.Char(
        string='Project Suffix', copy=False, tracking=True,
        help='Optional suffix, for example VO. Leave blank when no suffix is needed.'
    )
    dvz_include_so_number = fields.Boolean(
        string='Include SO Number in Project Name', default=True,
        help='Enabled: S00642 || AIB-EM-4128-VO. Disabled: AIB-EM-4128-VO.'
    )
    dvz_confirmed_project_code = fields.Char(readonly=True, copy=False)
    dvz_confirmed_project_name = fields.Char(readonly=True, copy=False)
    dvz_project_code = fields.Char(
        string='Project Code', compute='_compute_dvz_project_names', store=True, readonly=True
    )
    dvz_project_name = fields.Char(
        string='Generated Project Name', compute='_compute_dvz_project_names', store=True, readonly=True
    )

    @api.onchange('dvz_division_id')
    def _onchange_dvz_department_system(self):
        for order in self:
            if order.system and order.system.dvz_department_id != order.dvz_division_id:
                order.system = False

    @api.constrains('dvz_division_id', 'system')
    def _check_dvz_system_department(self):
        for order in self:
            if not order.system:
                continue
            if not order.dvz_division_id:
                raise ValidationError(_('Select the Department before selecting a System.'))
            if order.system.dvz_department_id != order.dvz_division_id:
                raise ValidationError(_(
                    'System %(system)s belongs to Department %(system_department)s, not %(order_department)s.',
                    system=order.system.display_name,
                    system_department=order.system.dvz_department_id.display_name or _('No Department'),
                    order_department=order.dvz_division_id.display_name,
                ))

    @api.depends('name', 'user_id.dvz_sales_abbreviation', 'dvz_division_id',
                 'dvz_project_reference', 'dvz_project_suffix', 'dvz_include_so_number',
                 'dvz_confirmed_project_code', 'dvz_confirmed_project_name')
    def _compute_dvz_project_names(self):
        for order in self:
            if order.dvz_confirmed_project_code:
                order.dvz_project_code = order.dvz_confirmed_project_code
                order.dvz_project_name = order.dvz_confirmed_project_name
                continue
            try:
                code = make_project_code(
                    order.user_id.dvz_sales_abbreviation, order.dvz_division_id.code,
                    order.dvz_project_reference, order.dvz_project_suffix,
                )
                name = make_project_name(order.name, code, order.dvz_include_so_number)
            except ValueError:
                code, name = False, False
            order.dvz_project_code = code
            order.dvz_project_name = name

    @api.model
    def _dvz_normalize_inputs(self, values):
        vals = dict(values)
        try:
            if 'dvz_project_reference' in vals:
                vals['dvz_project_reference'] = reference(vals['dvz_project_reference'], required=False) or False
            if 'dvz_project_suffix' in vals:
                vals['dvz_project_suffix'] = short_code(
                    vals['dvz_project_suffix'], 'Project suffix', required=False
                ) or False
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for original in vals_list:
            if any(original.get(field) for field in SNAPSHOT_FIELDS):
                raise UserError(_('Confirmed naming values are generated by confirmation, not imported.'))
            prepared.append(self._dvz_normalize_inputs(original))
        return super().create(prepared)

    def write(self, values):
        vals = self._dvz_normalize_inputs(values)
        if SNAPSHOT_FIELDS.intersection(vals):
            raise UserError(_('Confirmed naming values are managed automatically.'))
        for order in self.filtered('dvz_confirmed_project_code'):
            for field in NAMING_INPUTS.intersection(vals):
                old = order[field].id if field == 'dvz_division_id' else order[field]
                if (old or False) != (vals[field] or False):
                    raise UserError(_(
                        'Project naming was frozen when %(order)s was confirmed. '
                        'Do not change its identifiers retrospectively; duplicate the order for a new reference.',
                        order=order.name,
                    ))
        return super().write(vals)

    def _dvz_naming_requested(self):
        self.ensure_one()
        return bool(self.dvz_division_id or self.dvz_project_reference or self.dvz_project_suffix)

    def _dvz_validate_naming(self):
        self.ensure_one()
        if not self._dvz_naming_requested():
            return False
        if not self.dvz_division_id:
            raise UserError(_('Select a Division / Department before confirming %s.', self.name))
        if self.dvz_division_id.company_id != self.company_id:
            raise UserError(_('The division and the sales order must belong to the same company.'))
        if not self.dvz_division_id.active:
            raise UserError(_('Select an active division before confirming %s.', self.name))
        # if not self.user_id or not self.user_id.dvz_sales_abbreviation:
        #     raise UserError(_(
        #         'Set the Salesperson Abbreviation on the assigned salesperson user, then confirm %s.', self.name
        #     ))
        if not self.dvz_project_reference:
            raise UserError(_('Enter the Project Reference (for example 4128) before confirming %s.', self.name))
        try:
            return make_project_code(
                self.user_id.dvz_sales_abbreviation, self.dvz_division_id.code,
                self.dvz_project_reference, self.dvz_project_suffix,
            )
        except ValueError as exc:
            raise UserError(str(exc)) from exc

    def _dvz_freeze_project_naming(self):
        for order in self:
            if order.dvz_confirmed_project_code:
                continue
            code = order._dvz_validate_naming()
            if not code:
                continue
            name = make_project_name(order.name, code, order.dvz_include_so_number)
            # Bypass only this class's public snapshot guard; standard ORM rights/tracking still apply.
            super(SaleOrder, order).write({
                'dvz_confirmed_project_code': code,
                'dvz_confirmed_project_name': name,
            })

    def action_confirm(self):
        # Before core state changes: synchronous automated actions see the final name too.
        for order in self.filtered(lambda so: so.state in ('draft', 'sent')):
            order._dvz_freeze_project_naming()
        return super().action_confirm()

    def _dvz_project_naming_values(self):
        self.ensure_one()
        if self.state != 'sale' or not self._dvz_naming_requested():
            return {}
        self._dvz_freeze_project_naming()
        return {
            'name': self.dvz_confirmed_project_name,
            'dvz_origin_sale_id': self.id,
            'dvz_division_id': self.dvz_division_id.id,
            'dvz_project_code': self.dvz_confirmed_project_code,
        }

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type != 'form' or not arch.xpath("./sheet/group[@name='dvz_project_information']"):
            return arch, view
        # _get_view is cached across users before access-right postprocessing.
        # Use registry metadata, not fields_get() or a current-user group check.
        # The original groups/visibility scopes are preserved by the helper.
        arch = deepcopy(arch)
        metadata = {
            name: {'string': field.string, 'type': field.type}
            for name, field in self._fields.items()
        }
        report = regroup_project_fields(arch, metadata)
        # The System field comes from aala_rest_api. Enforce the department filter
        # on every visible occurrence after all inherited views have been combined.
        for node in arch.xpath(".//field[@name='system']"):
            node.set('domain', "[('dvz_department_id', '=', dvz_division_id)]")
            node.set('options', "{'no_quick_create': True}")
        if report['skipped']:
            _logger.warning(
                'DVZ Project Information: some fields were left in place in sale.order view %s: %s',
                view.id, report['skipped'],
            )
        return arch, view

    aala_division_ids = fields.Many2many(
        comodel_name='division.master',
        relation='aala_so_division_m2m_rel',
        column1='sale_order_id',
        column2='division_id',
        string='Division',
        help='Select one or more divisions for this quotation / sales order.',
    )

    aala_system_ids = fields.Many2many(
        comodel_name='system.master',
        relation='aala_so_system_m2m_rel',
        column1='sale_order_id',
        column2='system_id',
        string='System',
        domain="[('division', 'in', aala_division_ids)]",
        help='Only systems belonging to the selected divisions are available.',
    )

    @api.onchange('aala_division_ids')
    def _onchange_aala_division_ids(self):
        """Keep only systems that belong to one of the selected divisions."""
        for order in self:
            if not order.aala_division_ids:
                order.aala_system_ids = [(5, 0, 0)]
                continue
            valid_systems = order.aala_system_ids.filtered(
                lambda system: system.division in order.aala_division_ids
            )
            if valid_systems != order.aala_system_ids:
                order.aala_system_ids = valid_systems

    @api.onchange('aala_system_ids')
    def _onchange_aala_system_ids(self):
        """If systems are set programmatically, include their divisions as well."""
        for order in self:
            system_divisions = order.aala_system_ids.mapped('division')
            if system_divisions:
                order.aala_division_ids |= system_divisions

    def init(self):
        """Backfill existing single System data without deleting or changing it.

        The original sale.order.system Many2one remains untouched for compatibility.
        This only copies its current value to the new M2M fields and copies the
        corresponding system.master.division to the new Division M2M field.
        """
        self.env.cr.execute("""
                INSERT INTO aala_so_system_m2m_rel (sale_order_id, system_id)
                SELECT so.id, so.system
                  FROM sale_order so
                 WHERE so.system IS NOT NULL
                ON CONFLICT DO NOTHING
            """)
        self.env.cr.execute("""
                INSERT INTO aala_so_division_m2m_rel (sale_order_id, division_id)
                SELECT so.id, sm.division
                  FROM sale_order so
                  JOIN system_master sm ON sm.id = so.system
                 WHERE so.system IS NOT NULL
                   AND sm.division IS NOT NULL
                ON CONFLICT DO NOTHING
            """)

