from odoo import api, fields, models, _, Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero

from ..policy import OPERATOR_GROUP, INTERNAL_TOKEN


class MaterialReservation(models.Model):
    _name = 'dvz.material.reservation'
    _description = 'Project / Customer Material Reservation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(default='New', required=True, readonly=True, copy=False, index=True)
    source = fields.Selection([('sale', 'Sales Order'), ('manual', 'Manual Customer Hold')],
                              required=True, default='manual', readonly=True, copy=False, index=True)
    stage = fields.Selection([('draft', 'Draft'), ('active', 'Active'), ('cancel', 'Cancelled')],
                             default='draft', required=True, readonly=True, copy=False, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'), ('waiting', 'Waiting for Stock'), ('partial', 'Partly Reserved'),
        ('reserved', 'Fully Reserved'), ('released', 'Fully Released'),
        ('done', 'Completed'), ('cancel', 'Cancelled'),
    ], compute='_compute_state', store=True, index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company,
                                 index=True)
    sale_order_id = fields.Many2one('sale.order', readonly=True, copy=False, check_company=True,
                                    ondelete='restrict', index=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True,
                                 check_company=True, tracking=True, index=True)
    project_id = fields.Many2one('project.project', string='Project', check_company=True,
                                 tracking=True, index=True, ondelete='restrict')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Project',
                                          check_company=True, tracking=True, index=True,
                                          ondelete='restrict')
    project_link_note = fields.Char(string='Project Link Information', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', required=True, check_company=True)
    location_id = fields.Many2one('stock.location', string='Manual Hold Source', check_company=True,
                                  domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]")
    delivery_partner_id = fields.Many2one('res.partner', string='Delivery Address', check_company=True)
    manual_picking_id = fields.Many2one('stock.picking', readonly=True, copy=False, check_company=True)
    request_line_ids = fields.One2many('dvz.material.reservation.request', 'reservation_id',
                                       string='Manual Request Lines', copy=False)
    move_ids = fields.One2many('stock.move', 'dvz_reservation_id', string='Reservation Operations',
                               readonly=True, copy=False)
    event_ids = fields.One2many('dvz.material.reservation.event', 'reservation_id', readonly=True)
    move_count = fields.Integer(compute='_compute_counts')
    transfer_count = fields.Integer(compute='_compute_counts')
    has_picked_operations = fields.Boolean(compute='_compute_counts')
    notes = fields.Text()

    _sale_order_unique = models.Constraint('UNIQUE(sale_order_id)',
        'Only one material reservation document is allowed per Sales Order.')

    @api.depends('move_ids', 'move_ids.picking_id', 'move_ids.picked', 'move_ids.state')
    def _compute_counts(self):
        for reservation in self:
            reservation.move_count = len(reservation.move_ids)
            reservation.transfer_count = len(reservation.move_ids.picking_id)
            reservation.has_picked_operations = any(
                m.picked and m.state not in ('done', 'cancel') for m in reservation.move_ids)

    @api.depends('stage', 'move_ids.state', 'move_ids.dvz_reserved_qty',
                 'move_ids.dvz_target_qty', 'move_ids.dvz_shortage_qty', 'move_ids.dvz_held_back_qty')
    def _compute_state(self):
        for reservation in self:
            moves = reservation.move_ids
            active = moves.filtered(lambda m: m.state not in ('done', 'cancel'))
            if reservation.stage in ('draft', 'cancel'):
                state = reservation.stage
            elif not active:
                state = 'done' if any(m.state == 'done' for m in moves) else 'cancel' if moves else 'waiting'
            elif all(float_is_zero(m.dvz_target_qty, precision_rounding=m.product_uom.rounding) for m in active):
                state = 'released'
            elif all(float_is_zero(m.dvz_shortage_qty + m.dvz_held_back_qty, precision_rounding=m.product_uom.rounding) for m in active):
                state = 'reserved'
            elif any(m.dvz_reserved_qty > 0 for m in active):
                state = 'partial'
            else:
                state = 'waiting'
            reservation.state = state

    @api.model
    def _require_operator(self):
        if not self.env.su and not self.env.user.has_group(OPERATOR_GROUP):
            raise AccessError(_('Material Reservations: Manage Reservations permission is required.'))

    def _lock(self):
        self.check_access('write')
        if self:
            self.flush_recordset()
            self.env.cr.execute('SELECT id FROM dvz_material_reservation WHERE id IN %s ORDER BY id FOR UPDATE',
                                [tuple(self.ids)])
            self.invalidate_recordset()

    @api.model_create_multi
    def create(self, vals_list):
        internal = self.env.context.get('_dvz_material_internal') is INTERNAL_TOKEN
        if not internal:
            self._require_operator()
        prepared = []
        for values in vals_list:
            vals = dict(values)
            if not internal and (vals.get('source', 'manual') != 'manual' or vals.get('sale_order_id')
                                 or vals.get('stage', 'draft') != 'draft' or vals.get('manual_picking_id')):
                raise AccessError(_('Create manual holds in Draft. Sales Order reservations are generated by confirmation.'))
            company = self.env['res.company'].browse(vals.get('company_id', self.env.company.id))
            if not self.env.su and company not in self.env.companies:
                raise AccessError(_('The reservation company is not an allowed company.'))
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('dvz.material.reservation') or 'New'
            if not vals.get('delivery_partner_id'):
                vals['delivery_partner_id'] = vals.get('partner_id')
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        internal = self.env.context.get('_dvz_material_internal') is INTERNAL_TOKEN
        if not internal:
            self._require_operator()
            forbidden = {'source', 'stage', 'sale_order_id', 'manual_picking_id', 'name', 'move_ids', 'event_ids', 'project_link_note'}
            if forbidden.intersection(vals):
                raise AccessError(_('Use the reservation actions rather than changing its technical links or state.'))
            if any(r.stage != 'draft' for r in self) and {'partner_id', 'company_id', 'warehouse_id', 'location_id',
                                                         'delivery_partner_id', 'request_line_ids'}.intersection(vals):
                raise UserError(_('An active reservation cannot change customer, warehouse or request lines. Release/cancel it and create a new manual request.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Keep reservations for audit. Cancel a draft/manual reservation instead of deleting it.'))

    @api.onchange('warehouse_id')
    def _onchange_warehouse(self):
        for reservation in self:
            if reservation.warehouse_id:
                reservation.company_id = reservation.warehouse_id.company_id
                reservation.location_id = reservation.warehouse_id.lot_stock_id

    @api.onchange('project_id')
    def _onchange_project(self):
        for reservation in self:
            project = reservation.project_id
            if project:
                for name in ('account_id', 'analytic_account_id'):
                    field = project._fields.get(name)
                    if field and field.type == 'many2one' and field.comodel_name == 'account.analytic.account':
                        if project[name]:
                            reservation.analytic_account_id = project[name]
                        break

    @api.constrains('sale_order_id', 'company_id', 'partner_id', 'warehouse_id', 'location_id')
    def _check_consistency(self):
        for reservation in self:
            if reservation.sale_order_id and reservation.sale_order_id.company_id != reservation.company_id:
                raise ValidationError(_('The Sales Order and reservation must use the same company.'))
            if reservation.location_id and reservation.location_id.usage != 'internal':
                raise ValidationError(_('Manual holds must reserve from an internal stock location.'))
            if reservation.warehouse_id and reservation.warehouse_id.company_id != reservation.company_id:
                raise ValidationError(_('The warehouse and reservation must use the same company.'))

    def _log_event(self, action, reason, move=False, before=0.0, after=0.0):
        self.ensure_one()
        # Private method; callers check operation privileges and record access.
        self.env['dvz.material.reservation.event'].sudo().with_context(
            _dvz_material_internal=INTERNAL_TOKEN).create({
                'reservation_id': self.id, 'action': action, 'reason': reason,
                'actor_id': self.env.uid, 'move_id': move.id if move else False,
                'product_id': move.product_id.id if move else False,
                'uom_id': move.product_uom.id if move else False,
                'reserved_before': before, 'reserved_after': after,
            })

    def action_confirm_manual(self):
        self._require_operator()
        self._lock()
        for reservation in self:
            if reservation.source != 'manual' or reservation.stage != 'draft':
                raise UserError(_('Only a Draft manual reservation can be confirmed.'))
            if not reservation.request_line_ids:
                raise UserError(_('Add at least one stock-tracked product and quantity.'))
            warehouse = reservation.warehouse_id
            source = reservation.location_id or warehouse.lot_stock_id
            if not self.env['stock.location'].search_count([
                ('id', '=', source.id), ('id', 'child_of', warehouse.view_location_id.id),
                ('usage', '=', 'internal'), ('company_id', '=', reservation.company_id.id),
            ]):
                raise UserError(_('The manual source must be an internal location within the selected warehouse.'))
            partner = reservation.delivery_partner_id or reservation.partner_id
            destination = partner.with_company(reservation.company_id).property_stock_customer
            if not destination or destination.usage != 'customer':
                raise UserError(_('Configure a valid customer destination location for this delivery address.'))
            picking = self.env['stock.picking'].with_company(reservation.company_id).create({
                'partner_id': partner.id, 'picking_type_id': warehouse.out_type_id.id,
                'location_id': source.id, 'location_dest_id': destination.id,
                'company_id': reservation.company_id.id, 'origin': reservation.name,
            })
            vals = []
            for line in reservation.request_line_ids:
                line._check_request()
                vals.append({
                    'product_id': line.product_id.id,
                    'product_uom': line.uom_id.id, 'product_uom_qty': line.quantity,
                    'location_id': source.id, 'location_dest_id': destination.id,
                    'picking_id': picking.id, 'company_id': reservation.company_id.id,
                    'partner_id': partner.id, 'origin': reservation.name,
                    'procure_method': 'make_to_stock', 'dvz_reservation_id': reservation.id,
                })
            moves = self.env['stock.move'].with_context(_dvz_material_internal=INTERNAL_TOKEN).create(vals)
            moves._action_confirm(merge=False)
            reservation.with_context(_dvz_material_internal=INTERNAL_TOKEN).write({
                'stage': 'active', 'manual_picking_id': picking.id,
            })
            moves._action_assign()
            for move in moves.exists():
                reservation._log_event('reserve', _('Manual customer reservation confirmed.'),
                                       move, 0, move.dvz_reserved_qty)
        return True

    def action_reserve_available(self):
        self._require_operator()
        self._lock()
        for reservation in self:
            if reservation.stage != 'active':
                raise UserError(_('Confirm the manual request before reserving stock.'))
            moves = reservation.move_ids.filtered(lambda m: m.state not in ('done', 'cancel', 'draft') and not m.picked)
            moves._dvz_lock_rows()
            before = {m.id: m.dvz_reserved_qty for m in moves}
            moves._action_assign()
            for move in moves:
                reservation._log_event('reserve', _('Reserve available stock, respecting current limits.'),
                                       move, before[move.id], move.dvz_reserved_qty)
        return True

    def _adjust_action(self, mode):
        self.ensure_one()
        self._require_operator()
        self.check_access('read')
        moves = self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel', 'draft'))
        if not moves:
            raise UserError(_('There are no open stock operations to adjust.'))
        return moves._dvz_open_adjustment(mode)

    def action_release(self):
        return self._adjust_action('release')

    def action_set_target(self):
        return self._adjust_action('target')

    def action_release_selected(self):
        self._require_operator()
        self.check_access('write')
        moves = self.move_ids.filtered(lambda m: m.state not in ('draft', 'done', 'cancel'))
        return moves._dvz_open_adjustment('release')

    def action_cancel_manual(self):
        self._require_operator()
        self._lock()
        for reservation in self:
            if reservation.source != 'manual':
                raise UserError(_('Cancel the Sales Order through Sales. To free stock without cancelling it, use Release.'))
            if any(m.state == 'done' or m.picked for m in reservation.move_ids):
                raise UserError(_('This hold includes completed or picked operations. Use the normal return/stock workflow; cancellation cannot undo a delivery.'))
            reservation.move_ids.picking_id.action_cancel()
            reservation.with_context(_dvz_material_internal=INTERNAL_TOKEN).write({'stage': 'cancel'})
            reservation._log_event('cancel', _('Manual reservation cancelled; no delivery was performed.'))
        return True

    def action_view_moves(self):
        self.ensure_one()
        self.check_access('read')
        action = self.env['ir.actions.actions']._for_xml_id('dvz_material_reservation.action_reservation_operations')
        action.update(domain=[('dvz_reservation_id', '=', self.id)], context={'create': False})
        return action

    def action_view_transfers(self):
        self.ensure_one()
        self.check_access('read')
        action = self.env['ir.actions.actions']._for_xml_id('stock.action_picking_tree_all')
        action.update(domain=[('id', 'in', self.move_ids.picking_id.ids)], context={'create': False})
        return action

    def action_refresh_so_link(self):
        self.ensure_one()
        self._require_operator()
        self.check_access('write')
        if not self.sale_order_id:
            raise UserError(_('This manual hold has no Sales Order link. Set its project directly on this form.'))
        self.sale_order_id.check_access('read')
        values = self.sale_order_id._dvz_reservation_project_values()
        self.with_context(_dvz_material_internal=INTERNAL_TOKEN).write(values)
        self._log_event('link', _('Project/analytic link refreshed from the existing Sales Order configuration.'))
        return True


class MaterialReservationRequest(models.Model):
    _name = 'dvz.material.reservation.request'
    _description = 'Manual Material Reservation Request Line'
    _check_company_auto = True

    reservation_id = fields.Many2one('dvz.material.reservation', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='reservation_id.company_id', store=True, index=True)
    product_id = fields.Many2one('product.product', required=True, check_company=True,
                                 domain="[('is_storable', '=', True)]")
    quantity = fields.Float(default=1, required=True, digits='Product Unit')
    uom_id = fields.Many2one(related='product_id.uom_id', string='Unit', readonly=True)

    @api.constrains('product_id', 'quantity', 'reservation_id')
    def _check_request(self):
        from ..policy import finite_nonnegative
        for line in self:
            try:
                qty = finite_nonnegative(line.quantity)
            except (ValueError, TypeError):
                raise ValidationError(_('Quantity must be a finite positive number.'))
            if not line.product_id.is_storable or float_compare(qty, 0, precision_rounding=line.uom_id.rounding) <= 0:
                raise ValidationError(_('Select an inventory-tracked product and a positive quantity.'))
            if line.product_id.tracking == 'serial' and abs(qty - round(qty)) > 0.000001:
                raise ValidationError(_('Serial-tracked products require whole units.'))

    @api.model_create_multi
    def create(self, vals_list):
        self.env['dvz.material.reservation']._require_operator()
        for vals in vals_list:
            parent = self.env['dvz.material.reservation'].browse(vals.get('reservation_id'))
            parent.check_access('write')
            if parent.stage != 'draft' or parent.source != 'manual':
                raise UserError(_('Request lines can only be added to a Draft manual reservation.'))
        return super().create(vals_list)

    def write(self, vals):
        self.env['dvz.material.reservation']._require_operator()
        if 'reservation_id' in vals or any(r.stage != 'draft' for r in self.reservation_id):
            raise UserError(_('Do not change request lines after the hold is confirmed.'))
        return super().write(vals)

    def unlink(self):
        self.env['dvz.material.reservation']._require_operator()
        if any(r.stage != 'draft' for r in self.reservation_id):
            raise UserError(_('Confirmed request lines are retained for audit.'))
        return super().unlink()


class MaterialReservationEvent(models.Model):
    _name = 'dvz.material.reservation.event'
    _description = 'Material Reservation Audit Event'
    _order = 'id desc'

    reservation_id = fields.Many2one('dvz.material.reservation', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(related='reservation_id.company_id', store=True, index=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    actor_id = fields.Many2one('res.users', required=True, string='Changed By')
    action = fields.Selection([('reserve', 'Reserve'), ('release', 'Release'), ('target', 'Change Target'),
                               ('cancel', 'Cancel'), ('link', 'Project Link')], required=True)
    move_id = fields.Many2one('stock.move', ondelete='set null')
    product_id = fields.Many2one('product.product', ondelete='set null')
    uom_id = fields.Many2one('uom.uom', string='Unit', ondelete='set null')
    reserved_before = fields.Float(digits='Product Unit')
    reserved_after = fields.Float(digits='Product Unit')
    reason = fields.Text(required=True)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('_dvz_material_internal') is not INTERNAL_TOKEN:
            raise AccessError(_('Audit events are created only by reservation operations.'))
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_('Reservation audit events cannot be edited.'))

    def unlink(self):
        raise AccessError(_('Reservation audit events cannot be deleted.'))
