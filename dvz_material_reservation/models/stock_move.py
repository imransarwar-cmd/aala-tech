from odoo import api, fields, models, _, Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero, float_round

from ..policy import (
    INTERNAL_TOKEN, OPERATOR_GROUP, additional_to_reserve, effective_target,
    finite_nonnegative, quantity_columns, split_target,
)


class StockMove(models.Model):
    _inherit = 'stock.move'

    dvz_reservation_id = fields.Many2one('dvz.material.reservation', string='Material Reservation',
        readonly=True, copy=False, check_company=True, ondelete='restrict', index=True)
    dvz_reservation_limit_enabled = fields.Boolean(string='Reservation Limited', default=False,
        readonly=True, copy=False)
    dvz_reservation_limit_qty = fields.Float(string='Reservation Limit', digits='Product Unit',
        readonly=True, default=0, copy=False)
    dvz_reserved_qty = fields.Float(string='Reserved Qty', compute='_compute_dvz_quantities', store=True,
        digits='Product Unit', aggregator='sum')
    dvz_target_qty = fields.Float(string='Reservation Target', compute='_compute_dvz_quantities', store=True,
        digits='Product Unit', aggregator='sum')
    dvz_shortage_qty = fields.Float(string='Waiting for Stock', compute='_compute_dvz_quantities', store=True,
        digits='Product Unit', aggregator='sum')
    dvz_held_back_qty = fields.Float(string='Released / On Hold Qty', compute='_compute_dvz_quantities', store=True,
        digits='Product Unit', aggregator='sum')
    dvz_customer_id = fields.Many2one(related='dvz_reservation_id.partner_id', store=True, index=True,
        string='Reservation Customer')
    dvz_project_id = fields.Many2one(related='dvz_reservation_id.project_id', store=True, index=True,
        string='Reservation Project')
    dvz_analytic_account_id = fields.Many2one(related='dvz_reservation_id.analytic_account_id', store=True,
        index=True, string='Analytic Project')
    dvz_sale_order_id = fields.Many2one(related='dvz_reservation_id.sale_order_id', store=True, index=True,
        string='Reservation Sales Order')
    dvz_reservation_source = fields.Selection(related='dvz_reservation_id.source', store=True)

    @api.depends('product_uom_qty', 'quantity', 'state', 'dvz_reservation_id',
                 'dvz_reservation_limit_enabled', 'dvz_reservation_limit_qty')
    def _compute_dvz_quantities(self):
        for move in self:
            if not move.dvz_reservation_id:
                values = {'reserved': 0, 'target': 0, 'shortage': 0, 'on_hold': 0}
            else:
                values = quantity_columns(max(move.product_uom_qty, 0), max(move.quantity, 0),
                    move.dvz_reservation_limit_enabled, max(move.dvz_reservation_limit_qty, 0),
                    move.state in ('done', 'cancel'))
            move.dvz_reserved_qty = values['reserved']
            move.dvz_target_qty = values['target']
            move.dvz_shortage_qty = values['shortage']
            move.dvz_held_back_qty = values['on_hold']

    @api.constrains('dvz_reservation_id', 'company_id', 'dvz_reservation_limit_qty', 'sale_line_id')
    def _check_dvz_reservation(self):
        for move in self:
            try:
                finite_nonnegative(move.dvz_reservation_limit_qty)
            except (ValueError, TypeError):
                raise ValidationError(_('Reservation limits must be finite and non-negative.'))
            reservation = move.dvz_reservation_id
            if reservation and reservation.company_id != move.company_id:
                raise ValidationError(_('Stock operation and reservation must use the same company.'))
            if reservation and reservation.sale_order_id and move.sale_line_id and move.sale_line_id.order_id != reservation.sale_order_id:
                raise ValidationError(_('A stock operation cannot reserve materials for another Sales Order.'))

    def write(self, vals):
        controls = {'dvz_reservation_id', 'dvz_reservation_limit_enabled', 'dvz_reservation_limit_qty'}
        internal = self.env.context.get('_dvz_material_internal') is INTERNAL_TOKEN
        if controls.intersection(vals) and not internal and not self.env.su:
            # Even operators must use the checked wizard for cap changes.
            raise AccessError(_('Use the material reservation actions to change a reservation or its limit.'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        # Never silently attach a return to the original outgoing allocation.
        prepared = []
        for incoming in vals_list:
            vals = dict(incoming)
            if vals.get('origin_returned_move_id'):
                vals.update(dvz_reservation_id=False, dvz_reservation_limit_enabled=False,
                            dvz_reservation_limit_qty=0)
            prepared.append(vals)
        moves = super().create(prepared)
        for move in moves:
            if (move.dvz_reservation_id or move.origin_returned_move_id or
                    move.location_id.usage != 'internal' or not move.product_id.is_storable):
                continue
            reservation = self.env['dvz.material.reservation']
            if move.sale_line_id:
                reservation = reservation.sudo().search([
                    ('sale_order_id', '=', move.sale_line_id.order_id.id),
                    ('company_id', '=', move.company_id.id), ('stage', '=', 'active')], limit=1)
            if not reservation:
                parents = move.move_orig_ids.dvz_reservation_id
                if len(parents) == 1 and parents.company_id == move.company_id:
                    reservation = parents
            if reservation:
                move.with_context(_dvz_material_internal=INTERNAL_TOKEN).write({'dvz_reservation_id': reservation.id})
        return moves

    def _dvz_lock_rows(self):
        self.check_access('write')
        if not self:
            return
        self.flush_recordset()
        self.env.cr.execute('SELECT id FROM stock_move WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(self.ids)])
        self.invalidate_recordset(['state', 'picked', 'quantity', 'move_line_ids',
                                   'dvz_reservation_limit_enabled', 'dvz_reservation_limit_qty',
                                   'dvz_reserved_qty', 'dvz_target_qty'])
        self.move_line_ids.invalidate_recordset(['quantity', 'picked'])

    def _dvz_assert_adjustable(self):
        self.ensure_one()
        if not self.dvz_reservation_id:
            raise UserError(_('This operation is not part of a DVZ material reservation.'))
        if self.state in ('draft', 'done', 'cancel'):
            raise UserError(_('Only confirmed, unfinished stock operations can be reserved or released.'))
        if self.location_id.usage != 'internal' or not self.product_id.is_storable:
            raise UserError(_('Only inventory-tracked materials at internal stock locations can be reserved.'))
        if self.picked or any(self.move_line_ids.mapped('picked')):
            raise UserError(_('Materials already marked Picked cannot be released here. Correct the picking through Inventory first.'))

    def _dvz_validate_target(self, quantity):
        self.ensure_one()
        try:
            quantity = finite_nonnegative(quantity)
        except (ValueError, TypeError):
            raise ValidationError(_('Enter a finite, non-negative quantity.'))
        if float_compare(quantity, self.product_uom_qty, precision_rounding=self.product_uom.rounding) > 0:
            raise ValidationError(_('The reservation target cannot exceed this operation\'s demand.'))
        rounded = float_round(quantity, precision_rounding=self.product_uom.rounding)
        if abs(rounded - quantity) > max(0.0000001, self.product_uom.rounding / 1000):
            raise ValidationError(_('Use a quantity compatible with the operation unit rounding.'))
        base_qty = self.product_uom._compute_quantity(quantity, self.product_id.uom_id, round=False)
        if self.product_id.tracking == 'serial' and abs(base_qty - round(base_qty)) > 0.000001:
            raise ValidationError(_('Serial-tracked products can only be reserved or released in whole units.'))
        return rounded

    def _dvz_release_to(self, keep_qty):
        """Reduce only unprocessed move lines using the ORM; never edit quants directly.

        Keeps the identity of the retained lots/serials, owners and locations.
        Does NOT lower stock.move demand or sale.order.line ordered quantity.
        """
        self.ensure_one()
        self._dvz_assert_adjustable()
        keep_qty = self._dvz_validate_target(keep_qty)
        current = self.quantity
        if float_compare(keep_qty, current, precision_rounding=self.product_uom.rounding) > 0:
            raise UserError(_('The quantity to keep is greater than the current reservation.'))
        if float_is_zero(keep_qty, precision_rounding=self.product_uom.rounding):
            self._do_unreserve()
            return
        release = current - keep_qty
        if float_is_zero(release, precision_rounding=self.product_uom.rounding):
            return
        if any(ml.result_package_id or ml.is_entire_pack for ml in self.move_line_ids):
            raise UserError(_('For a partial release, unpack entire/result packages through Inventory first. A full release is supported.'))
        for line in self.move_line_ids.sorted('id', reverse=True):
            if float_is_zero(release, precision_rounding=self.product_uom.rounding):
                break
            line_qty = line.product_uom_id._compute_quantity(line.quantity, self.product_uom, round=False)
            if float_compare(line_qty, release, precision_rounding=self.product_uom.rounding) <= 0:
                release = max(0.0, release - line_qty)
                line.unlink()
            else:
                new_qty = self.product_uom._compute_quantity(line_qty - release, line.product_uom_id, round=False)
                representable = float_round(new_qty, precision_rounding=line.product_uom_id.rounding)
                if abs(representable - new_qty) > max(0.0000001, line.product_uom_id.rounding / 1000):
                    raise UserError(_('The requested release cannot be represented in the reserved line unit. Use a compatible quantity.'))
                line.write({'quantity': representable})
                release = 0.0
        self._recompute_state()
        if not float_is_zero(release, precision_rounding=self.product_uom.rounding):
            raise UserError(_('Stock changed during release. No partial change is kept; reload and retry.'))

    def _dvz_set_target(self, target, reason, action='target'):
        self.ensure_one()
        self.env['dvz.material.reservation']._require_operator()
        self._dvz_assert_adjustable()
        target = self._dvz_validate_target(target)
        before = self.quantity
        if float_compare(before, target, precision_rounding=self.product_uom.rounding) > 0:
            self._dvz_release_to(target)
        self.with_context(_dvz_material_internal=INTERNAL_TOKEN).write({
            'dvz_reservation_limit_enabled': True,
            'dvz_reservation_limit_qty': target,
        })
        if action == 'target':
            self._action_assign()
        self.dvz_reservation_id._log_event(action, reason, self, before, self.quantity)

    def _action_assign(self, force_qty=False):
        limited = self.filtered(lambda m: m.dvz_reservation_id and m.dvz_reservation_limit_enabled)
        normal = self - limited
        if normal:
            super(StockMove, normal)._action_assign(force_qty=force_qty)
        limited = limited.filtered(lambda m: m.state in ('confirmed', 'waiting', 'partially_available', 'assigned') and not m.picked)
        if limited:
            limited._dvz_lock_rows()
        for move in limited:
            if move.state not in ('confirmed', 'waiting', 'partially_available', 'assigned') or move.picked:
                continue
            missing = additional_to_reserve(move.product_uom_qty, move.quantity, True,
                                            move.dvz_reservation_limit_qty, force_qty)
            if float_is_zero(missing, precision_rounding=move.product_uom.rounding):
                continue
            # In Odoo 19 force_qty is an ADDITIONAL quantity, not a total.
            super(StockMove, move)._action_assign(force_qty=missing)
            # Core force assignment may label a limited quantity Assigned.
            # Restore the state relative to the UNCHANGED original demand.
            move._recompute_state()
        return None

    @api.model
    def _prepare_merge_moves_distinct_fields(self):
        return super()._prepare_merge_moves_distinct_fields() + [
            'dvz_reservation_id', 'dvz_reservation_limit_enabled']

    def _merge_moves_fields(self):
        vals = super()._merge_moves_fields()
        if self and all(self.mapped('dvz_reservation_limit_enabled')):
            vals['dvz_reservation_limit_qty'] = sum(
                effective_target(m.product_uom_qty, True, m.dvz_reservation_limit_qty) for m in self)
        return vals

    def _merge_moves(self, merge_into=False):
        # Private core operation; its derived limit update is not a user bypass.
        result = super(StockMove, self.with_context(
            _dvz_material_internal=INTERNAL_TOKEN,
            _dvz_material_merging=INTERNAL_TOKEN,
        ))._merge_moves(merge_into=merge_into)
        result = result.with_context(self.env.context)
        result.move_line_ids._dvz_check_limit()
        return result

    def _prepare_move_split_vals(self, qty):
        vals = super()._prepare_move_split_vals(qty)
        if self.dvz_reservation_id:
            vals['dvz_reservation_id'] = self.dvz_reservation_id.id
        if self.dvz_reservation_limit_enabled:
            new_uom = self.env['uom.uom'].browse(self.env.context.get('force_split_uom_id')) or self.product_uom
            split_in_old_uom = new_uom._compute_quantity(qty, self.product_uom, round=False)
            new_target = split_target(self.product_uom_qty, self.dvz_reservation_limit_qty, split_in_old_uom)
            vals.update(
                dvz_reservation_limit_enabled=True,
                dvz_reservation_limit_qty=self.product_uom._compute_quantity(new_target, new_uom, round=False),
            )
        return vals

    def _dvz_open_adjustment(self, mode):
        self.env['dvz.material.reservation']._require_operator()
        self.check_access('write')
        if not self:
            raise UserError(_('Select at least one open reservation operation.'))
        for move in self:
            move._dvz_assert_adjustable()
        if len(self.company_id) > 1:
            raise UserError(_('Adjust one company at a time.'))
        wizard = self.env['dvz.reservation.adjust'].create({
            'mode': mode,
            'company_id': self.company_id.id,
            'line_ids': [Command.create({
                'move_id': m.id,
                'quantity': m.dvz_reserved_qty if mode == 'release' else m.product_uom_qty,
            }) for m in self],
        })
        return {'type': 'ir.actions.act_window', 'name': _('Release / Adjust Reservation'),
                'res_model': 'dvz.reservation.adjust', 'view_mode': 'form',
                'res_id': wizard.id, 'target': 'new'}

    def action_dvz_release(self):
        return self._dvz_open_adjustment('release')

    def action_dvz_set_target(self):
        return self._dvz_open_adjustment('target')

    def action_dvz_reservation_details(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Reserved Lots / Locations'),
                'res_model': 'stock.move.line', 'view_mode': 'list,form',
                'domain': [('move_id', '=', self.id)], 'context': {'create': False}}


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.constrains('quantity', 'move_id')
    def _dvz_check_limit(self):
        if self.env.context.get('_dvz_material_merging') is INTERNAL_TOKEN:
            # Core first moves the lines, then writes the combined demand/cap.
            # _merge_moves performs this check again after the final write.
            return
        # Prevent a detailed-operation edit from silently exceeding a released
        # operation's cap. Native inventory ACLs continue to apply.
        for move in self.move_id.filtered(lambda m: m.dvz_reservation_id and m.dvz_reservation_limit_enabled and m.state not in ('done', 'cancel')):
            qty = sum(line.product_uom_id._compute_quantity(line.quantity, move.product_uom, round=False)
                      for line in move.move_line_ids)
            target = effective_target(move.product_uom_qty, True, move.dvz_reservation_limit_qty)
            if float_compare(qty, target, precision_rounding=move.product_uom.rounding) > 0:
                raise ValidationError(_('This operation exceeds its reservation limit. Use Set Reservation Target first.'))


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def do_unreserve(self):
        # Keep the standard transfer Unreserve button consistent with the
        # reservation register. Cancellation uses stock.move._do_unreserve
        # internally and remains the native cancellation workflow.
        self.check_access('write')
        managed = self.move_ids.filtered(lambda m: m.dvz_reservation_id and m.state not in ('draft', 'done', 'cancel'))
        if managed:
            self.env['dvz.material.reservation']._require_operator()
            managed.dvz_reservation_id._lock()
            managed._dvz_lock_rows()
            for move in managed:
                move._dvz_assert_adjustable()
            for move in managed:
                move._dvz_set_target(0, _('Released using the transfer Unreserve action.'), 'release')
        return super().do_unreserve()
