"""Read-only sourcing report on native sales lines.

Native delivery quantities remain authoritative. No stock is reserved, moved,
unreserved or bought by this module. Absence of a purchase link is not proof
that a delivery used stock that existed when the order was confirmed.
"""
from markupsafe import Markup, escape

from odoo import api, Command, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from ..services.quantity_math import (
    manual_split_warnings, reconcile_source_quantities, validate_manual_split,
)


SOURCE_FIELDS = frozenset({
    'dvz_source_override', 'dvz_manual_stock_qty', 'dvz_manual_purchase_qty',
    'dvz_manual_stock_used_qty', 'dvz_manual_purchase_used_qty', 'dvz_source_note',
    'dvz_source_purchase_line_ids', 'dvz_source_product_id', 'dvz_source_uom_id',
    'dvz_source_ordered_at_entry', 'dvz_source_delivered_at_entry',
    'dvz_source_updated_by', 'dvz_source_updated_at',
})


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dvz_order_date = fields.Datetime(
        related='order_id.date_order', string='Order Date', store=True, index=True,
        compute_sudo=False, groups='base.group_user')
    dvz_customer_id = fields.Many2one(
        related='order_id.partner_id', string='Customer', store=True, index=True,
        compute_sudo=False, groups='base.group_user')
    dvz_salesperson_id = fields.Many2one(
        related='order_id.user_id', string='Salesperson', store=True, index=True,
        compute_sudo=False, groups='base.group_user')
    dvz_warehouse_id = fields.Many2one(
        related='warehouse_id', string='Warehouse', store=True, compute_sudo=False, groups='base.group_user')
    dvz_product_code = fields.Char(
        related='product_id.default_code', string='Product Code', compute_sudo=False, groups='base.group_user')

    dvz_pending_qty = fields.Float(
        string='Pending Qty', compute='_compute_dvz_supply', digits='Product Unit',
        compute_sudo=False, aggregator=False, groups='base.group_user')
    dvz_overdelivered_qty = fields.Float(
        string='Overdelivered Qty', compute='_compute_dvz_supply', digits='Product Unit',
        compute_sudo=False, aggregator=False, groups='base.group_user')
    dvz_reserved_qty = fields.Float(
        string='Reserved Now', compute='_compute_dvz_supply', digits='Product Unit',
        compute_sudo=False, aggregator=False,
        help='Open warehouse reservations attributable to this line, capped at pending demand. '
             'This is not evidence of pre-order stock or a delivery.', groups='base.group_user')
    dvz_available_qty = fields.Float(
        string='Warehouse Free Qty', compute='_compute_dvz_supply', digits='Product Unit',
        compute_sudo=False, aggregator=False,
        help='Current unreserved warehouse stock in this sales line unit. Informational only; '
             'the same warehouse balance may appear on several lines. Never sum this column.', groups='base.group_user')
    dvz_stock_qty = fields.Float(
        string='From Stock Qty', compute='_compute_dvz_supply', digits='Product Unit',
        compute_sudo=False, aggregator=False,
        help='Recorded supply from existing stock. Includes the recorded delivered portion. '
             'This is a sourcing declaration, not an inventory reservation.', groups='base.group_user')
    dvz_purchase_qty = fields.Float(
        string='From Purchase Qty', compute='_compute_dvz_supply', digits='Product Unit',
        compute_sudo=False, aggregator=False,
        help='Recorded purchase supply or a fully traceable exclusive purchase chain. '
             'A shortage is never automatically presented as a purchase order.', groups='base.group_user')
    dvz_total_source_qty = fields.Float(
        string='Total Sourced Qty', compute='_compute_dvz_supply', digits='Product Unit',
        compute_sudo=False, aggregator=False,
        help='From Stock Qty + From Purchase Qty; not Ordered Qty + Delivered Qty.', groups='base.group_user')
    dvz_shortage_qty = fields.Float(
        string='Source Unassigned Qty', compute='_compute_dvz_supply', digits='Product Unit',
        compute_sudo=False, aggregator=False,
        help='Ordered quantity without a confirmed/recorded source split. This can include '
             'stock already reserved or delivered with unknown origin; it is not a buy instruction.', groups='base.group_user')
    dvz_stock_used_qty = fields.Float(
        string='Delivered from Stock', compute='_compute_dvz_supply', digits='Product Unit',
        compute_sudo=False, aggregator=False, groups='base.group_user')
    dvz_purchase_used_qty = fields.Float(
        string='Delivered from Purchase', compute='_compute_dvz_supply', digits='Product Unit',
        compute_sudo=False, aggregator=False, groups='base.group_user')
    dvz_unclassified_used_qty = fields.Float(
        string='Delivered Source Unknown', compute='_compute_dvz_supply', digits='Product Unit',
        compute_sudo=False, aggregator=False, groups='base.group_user')
    dvz_source_basis = fields.Char(
        string='Source Basis / Review', compute='_compute_dvz_supply', compute_sudo=False, groups='base.group_user')
    dvz_po_refs = fields.Char(
        string='Purchase Orders', compute='_compute_dvz_supply', compute_sudo=False, groups='base.group_user')

    dvz_source_override = fields.Boolean(string='Recorded Source Split', copy=False, groups='base.group_user')
    dvz_manual_stock_qty = fields.Float(string='Recorded Stock Supply', digits='Product Unit', copy=False, groups='base.group_user')
    dvz_manual_purchase_qty = fields.Float(string='Recorded Purchase Supply', digits='Product Unit', copy=False, groups='base.group_user')
    dvz_manual_stock_used_qty = fields.Float(string='Recorded Stock Delivered', digits='Product Unit', copy=False, groups='base.group_user')
    dvz_manual_purchase_used_qty = fields.Float(string='Recorded Purchase Delivered', digits='Product Unit', copy=False, groups='base.group_user')
    dvz_source_note = fields.Text(string='Source Evidence / Note', copy=False, groups='base.group_user')
    dvz_source_purchase_line_ids = fields.Many2many(
        'purchase.order.line', 'dvz_sale_supply_po_rel', 'sale_line_id', 'purchase_line_id',
        string='Supporting Purchase Lines', copy=False,
        help='Supporting references only; these links do not reserve or exclusively allocate a PO.', groups='base.group_user')
    dvz_source_product_id = fields.Many2one('product.product', copy=False, readonly=True, groups='base.group_user')
    dvz_source_uom_id = fields.Many2one('uom.uom', copy=False, readonly=True, groups='base.group_user')
    dvz_source_ordered_at_entry = fields.Float(digits='Product Unit', copy=False, readonly=True, groups='base.group_user')
    dvz_source_delivered_at_entry = fields.Float(digits='Product Unit', copy=False, readonly=True, groups='base.group_user')
    dvz_source_updated_by = fields.Many2one('res.users', string='Source Recorded By', copy=False, readonly=True, groups='base.group_user')
    dvz_source_updated_at = fields.Datetime(string='Source Recorded On', copy=False, readonly=True, groups='base.group_user')

    @api.depends(
        'product_id', 'product_uom_id', 'product_uom_qty', 'qty_delivered', 'state',
        'warehouse_id', 'company_id', 'move_ids.state', 'move_ids.quantity',
        'move_ids.product_uom_qty', 'move_ids.move_orig_ids', 'move_ids.purchase_line_id',
        'dvz_source_override', 'dvz_manual_stock_qty', 'dvz_manual_purchase_qty',
        'dvz_manual_stock_used_qty', 'dvz_manual_purchase_used_qty',
        'dvz_source_product_id', 'dvz_source_uom_id', 'dvz_source_purchase_line_ids',
        'dvz_source_ordered_at_entry', 'dvz_source_delivered_at_entry',
    )
    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_dvz_supply(self):
        free_by_product_warehouse, unavailable_stock = self._dvz_free_stock_map()
        for line in self:
            stock_plan = purchase_plan = stock_used = purchase_used = reserved = available = 0.0
            po_refs = ''
            messages = []
            precision = line._dvz_precision()
            physical = bool(line.product_id and line.product_id.type == 'consu' and not line.display_type)
            if physical:
                try:
                    reserved = line._dvz_reserved_now()
                    key = (line.product_id.id, line.company_id.id, line.warehouse_id.id)
                    if key in unavailable_stock:
                        messages.append(_('Free-stock figure unavailable with your access rights'))
                    available = line.product_id.uom_id._compute_quantity(
                        free_by_product_warehouse.get(key, 0.0), line.product_uom_id, round=False)
                except AccessError:
                    messages.append(_('Inventory details unavailable with your access rights'))

                if line.dvz_source_override:
                    if (line.dvz_source_product_id != line.product_id
                            or line.dvz_source_uom_id != line.product_uom_id):
                        messages.append(_('Review required: product/unit changed; record the source split again'))
                    else:
                        stock_plan = line.dvz_manual_stock_qty
                        purchase_plan = line.dvz_manual_purchase_qty
                        stock_used = line.dvz_manual_stock_used_qty
                        purchase_used = line.dvz_manual_purchase_used_qty
                        messages.append(_('Recorded source split'))
                        problems = manual_split_warnings(
                            line.product_uom_qty, line.qty_delivered, stock_plan,
                            purchase_plan, stock_used, purchase_used, precision)
                        if problems:
                            messages.append(_('Review required: %s', '; '.join(problems)))
                        if (abs(line.product_uom_qty - line.dvz_source_ordered_at_entry) > precision
                                or abs(line.qty_delivered - line.dvz_source_delivered_at_entry) > precision):
                            messages.append(_('Quantities changed since recording; review the split'))
                        if abs(line.qty_delivered - line.dvz_source_delivered_at_entry) > precision:
                            # A new delivery or return can change the net source
                            # mix. Keep the original entry for review, but never
                            # show stale usage as the current delivered split.
                            stock_used = purchase_used = 0.0
                        try:
                            pos = line.dvz_source_purchase_line_ids
                            if pos:
                                pos.check_access('read')
                                pos.order_id.check_access('read')
                                po_refs = ', '.join(sorted(set(pos.order_id.mapped('name'))))
                                if any(po.state not in ('purchase', 'done') for po in pos.order_id):
                                    messages.append(_('Review required: a supporting PO is not confirmed or was cancelled'))
                                if any(po.product_id != line.product_id or po.company_id != line.company_id for po in pos):
                                    messages.append(_('Review required: a supporting PO product/company changed'))
                        except AccessError:
                            messages.append(_('Supporting PO references restricted'))
                else:
                    try:
                        purchase_plan, purchase_used, po_refs, inaccessible = line._dvz_auto_purchase_source()
                        if inaccessible:
                            messages.append(_('Purchase trace restricted by access rights'))
                    except AccessError:
                        purchase_plan = purchase_used = 0.0
                        messages.append(_('Purchase trace restricted by access rights'))
                    if purchase_plan > precision or purchase_used > precision:
                        messages.append(_('Exclusive linked purchase chain; other sources unverified'))
                    else:
                        messages.append(_('Source unverified: record stock/purchase split'))
                if line.state == 'cancel':
                    messages.append(_('Cancelled order; source entries are historical'))
            else:
                messages.append(_('Not applicable: service or non-physical line'))

            values = reconcile_source_quantities(
                line.product_uom_qty, line.qty_delivered, stock_plan, purchase_plan,
                stock_used, purchase_used, precision)
            line.dvz_pending_qty = values['pending_qty']
            line.dvz_overdelivered_qty = values['overdelivered_qty']
            line.dvz_reserved_qty = reserved
            line.dvz_available_qty = available
            line.dvz_stock_qty = stock_plan
            line.dvz_purchase_qty = purchase_plan
            line.dvz_total_source_qty = values['total_source_qty']
            line.dvz_shortage_qty = values['shortage_qty'] if physical else 0.0
            line.dvz_stock_used_qty = stock_used
            line.dvz_purchase_used_qty = purchase_used
            line.dvz_unclassified_used_qty = values['unclassified_used_qty'] if physical else 0.0
            line.dvz_source_basis = '; '.join(messages)
            line.dvz_po_refs = po_refs

    def _dvz_free_stock_map(self):
        """Read one stock batch per company/warehouse rather than per sales line."""
        groups = {}
        for line in self:
            if line.product_id and line.product_id.is_storable and not line.display_type:
                key = (line.company_id.id, line.warehouse_id.id)
                groups.setdefault(key, set()).add(line.product_id.id)
        quantities = {}
        unavailable = set()
        for (company_id, warehouse_id), product_ids in groups.items():
            products = self.env['product.product'].browse(list(product_ids)).with_company(company_id).with_context(
                allowed_company_ids=[company_id], warehouse_id=warehouse_id,
                location=False, to_date=False, from_date=False,
                lot_id=False, owner_id=False, package_id=False)
            try:
                for row in products.read(['free_qty']):
                    quantities[(row['id'], company_id, warehouse_id)] = row['free_qty']
            except AccessError:
                unavailable.update((product_id, company_id, warehouse_id) for product_id in product_ids)
        return quantities, unavailable

    def _dvz_precision(self):
        self.ensure_one()
        # This is a numerical comparison tolerance, not a whole-unit allowance.
        return max((self.product_uom_id.rounding or 0.01) * 0.000001, 1e-9)

    def _dvz_move_qty(self, move, done=False):
        self.ensure_one()
        return move.product_uom._compute_quantity(
            move.quantity if done else move.product_uom_qty,
            self.product_uom_id, round=False)

    def _dvz_reserved_now(self):
        """Count physical open reservations, never the entire warehouse balance."""
        self.ensure_one()
        pending = max(self.product_uom_qty - self.qty_delivered, 0.0)
        if self.state != 'sale' or not self.product_id.is_storable or not pending:
            return 0.0
        moves = self.move_ids.filtered(
            lambda m: m.product_id == self.product_id and m.company_id == self.company_id
            and m.state not in ('draft', 'cancel', 'done') and not m.origin_returned_move_id)
        # 19.0 normally propagates sale_line_id to the route. Only include an
        # unlabelled upstream step when it has a unique path to this sale line.
        seen = set(moves.ids)
        frontier = list(moves)
        for _depth in range(100):
            if not frontier:
                break
            next_frontier = []
            for downstream in frontier:
                for origin in downstream.move_orig_ids:
                    if origin.id in seen:
                        continue
                    seen.add(origin.id)
                    if (origin.product_id != self.product_id or origin.company_id != self.company_id
                            or origin.state in ('draft', 'cancel', 'done') or origin.origin_returned_move_id):
                        continue
                    consumers = origin.move_dest_ids.filtered(lambda m: m.state != 'cancel')
                    if consumers != downstream or (origin.sale_line_id and origin.sale_line_id != self):
                        continue
                    moves |= origin
                    next_frontier.append(origin)
            frontier = next_frontier
        total = sum(self._dvz_move_qty(move, done=True) for move in moves
                    if move.location_id.usage == 'internal' and move.quantity > 0)
        return min(max(total, 0.0), pending)

    def _dvz_exact_purchase_line(self, move, qty, done=False):
        """Return a PO only for a sufficient, single-parent, exclusive chain.

        Conservative by design: no quantities are apportioned between merged
        parents or shared downstream moves. Generic stock receipts remain unknown.
        """
        self.ensure_one()
        empty = self.env['purchase.order.line']
        seen = set()
        current = move
        precision = self._dvz_precision()
        while current and current.id not in seen and len(seen) < 100:
            seen.add(current.id)
            if (current.state == 'cancel' or current.product_id != self.product_id
                    or current.company_id != self.company_id
                    or (done and current.state != 'done')):
                return empty
            if self._dvz_move_qty(current, done=done) + precision < qty:
                return empty
            if current.purchase_line_id:
                po_line = current.purchase_line_id
                po_line.check_access('read')
                po_line.order_id.check_access('read')
                if (po_line.product_id == self.product_id and po_line.company_id == self.company_id
                        and po_line.order_id.state in ('purchase', 'done')):
                    # Count this outgoing move quantity, never the entire PO.
                    return po_line
                return empty
            origins = current.move_orig_ids.filtered(lambda m: m.state != 'cancel')
            if len(origins) != 1:
                return empty
            parent = origins[0]
            if done and (parent.date > current.date or parent.location_dest_id != current.location_id):
                # A purchase received after a forced delivery cannot be the
                # proven source of that earlier delivery.
                return empty
            consumers = parent.move_dest_ids.filtered(lambda m: m.state != 'cancel')
            if consumers != current:
                return empty
            if parent.sale_line_id and parent.sale_line_id != self:
                return empty
            current = parent
        return empty

    def _dvz_auto_purchase_source(self):
        self.ensure_one()
        if self.qty_delivered_method != 'stock_move':
            return 0.0, 0.0, '', False
        outgoing, incoming = self._get_outgoing_incoming_moves()
        planned = used = 0.0
        po_lines = self.env['purchase.order.line']
        inaccessible = False
        for move in outgoing:
            if move.state in ('cancel', 'draft'):
                continue
            done = move.state == 'done'
            qty = self._dvz_move_qty(move, done=done)
            if qty <= 0:
                continue
            try:
                po_line = self._dvz_exact_purchase_line(move, qty, done=done)
            except AccessError:
                inaccessible = True
                continue
            if po_line:
                planned += qty
                used += qty if done else 0.0
                po_lines |= po_line
        for move in incoming:
            if move.state != 'done':
                continue
            # Match the official sale_stock delivered-quantity skip condition.
            if (not move.origin_returned_move_id and not move.location_id._is_outgoing()
                    and self.product_uom_qty > 0 and not move.picking_id.return_id):
                continue
            qty = self._dvz_move_qty(move, done=True)
            origin = move.origin_returned_move_id
            if not origin:
                # An unidentified return could be from either source. Avoid
                # overstating the remaining purchase-sourced delivery.
                used = max(used - qty, 0.0)
                planned = max(planned - qty, 0.0)
                continue
            try:
                po_line = self._dvz_exact_purchase_line(origin, qty, done=True)
            except AccessError:
                inaccessible = True
                po_line = self.env['purchase.order.line']
            if po_line:
                used -= qty
                planned -= qty
        used = min(max(used, 0.0), max(self.qty_delivered, 0.0))
        planned = min(max(planned, used, 0.0), max(self.product_uom_qty, self.qty_delivered, 0.0))
        refs = ', '.join(sorted(set(po_lines.order_id.mapped('name'))))
        return planned, used, refs, inaccessible

    def _dvz_require_source_manager(self):
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise AccessError(_('Only a Sales Administrator can record or clear the source split.'))

    @api.model_create_multi
    def create(self, vals_list):
        source_defaults = any('default_' + name in self.env.context for name in SOURCE_FIELDS)
        changes_source = source_defaults or any(SOURCE_FIELDS.intersection(vals) for vals in vals_list)
        if changes_source:
            self._dvz_require_source_manager()
        lines = super().create(vals_list)
        if changes_source:
            lines._dvz_validate_recorded_source()
        return lines

    def write(self, vals):
        changes_source = bool(SOURCE_FIELDS.intersection(vals))
        if changes_source:
            self._dvz_require_source_manager()
        result = super().write(vals)
        if changes_source:
            self._dvz_validate_recorded_source()
        return result

    def _dvz_validate_recorded_source(self):
        for line in self.filtered('dvz_source_override'):
            if line.display_type or not line.product_id or line.product_id.type != 'consu':
                raise ValidationError(_('Source splits are for physical product lines only.'))
            if not (line.dvz_source_note or '').strip():
                raise ValidationError(_('Enter a source evidence note for the recorded quantities.'))
            if (line.dvz_source_product_id != line.product_id
                    or line.dvz_source_uom_id != line.product_uom_id):
                raise ValidationError(_('Record the source split using the current product and unit.'))
            try:
                validate_manual_split(
                    line.product_uom_qty, line.qty_delivered, line.dvz_manual_stock_qty,
                    line.dvz_manual_purchase_qty, line.dvz_manual_stock_used_qty,
                    line.dvz_manual_purchase_used_qty, line._dvz_precision())
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            pos = line.dvz_source_purchase_line_ids
            if pos:
                pos.check_access('read')
                pos.order_id.check_access('read')
                if any(p.company_id != line.company_id or p.product_id != line.product_id
                       or p.order_id.state not in ('purchase', 'done') for p in pos):
                    raise ValidationError(_('Supporting purchase lines must be confirmed and use the same product and company.'))

    def _dvz_apply_source_split(self, stock_plan, purchase_plan, stock_used,
                                purchase_used, note, purchase_lines=None):
        self.ensure_one()
        self._dvz_require_source_manager()
        self.check_access('write')
        pos = purchase_lines if purchase_lines is not None else self.env['purchase.order.line']
        if pos:
            pos.check_access('read')
        self.write({
            'dvz_source_override': True,
            'dvz_manual_stock_qty': stock_plan, 'dvz_manual_purchase_qty': purchase_plan,
            'dvz_manual_stock_used_qty': stock_used, 'dvz_manual_purchase_used_qty': purchase_used,
            'dvz_source_note': (note or '').strip(),
            'dvz_source_purchase_line_ids': [Command.set(pos.ids)],
            'dvz_source_product_id': self.product_id.id,
            'dvz_source_uom_id': self.product_uom_id.id,
            'dvz_source_ordered_at_entry': self.product_uom_qty,
            'dvz_source_delivered_at_entry': self.qty_delivered,
            'dvz_source_updated_by': self.env.user.id,
            'dvz_source_updated_at': fields.Datetime.now(),
        })
        self.order_id.message_post(subtype_xmlid='mail.mt_note', body=Markup(
            '<p><strong>Sales source split recorded</strong></p>'
            '<p>%s — supply: stock %s; purchase %s. Delivered: stock %s; purchase %s.</p><p>%s</p>'
        ) % tuple(escape(value) for value in (
            self.product_id.display_name, stock_plan, purchase_plan, stock_used, purchase_used, note)))

    def action_dvz_clear_source_split(self):
        self._dvz_require_source_manager()
        self.check_access('write')
        self.write({
            'dvz_source_override': False, 'dvz_manual_stock_qty': 0.0,
            'dvz_manual_purchase_qty': 0.0, 'dvz_manual_stock_used_qty': 0.0,
            'dvz_manual_purchase_used_qty': 0.0, 'dvz_source_note': False,
            'dvz_source_purchase_line_ids': [Command.clear()],
            'dvz_source_product_id': False, 'dvz_source_uom_id': False,
            'dvz_source_updated_by': self.env.user.id,
            'dvz_source_updated_at': fields.Datetime.now(),
        })
        for line in self:
            line.order_id.message_post(subtype_xmlid='mail.mt_note', body=_(
                'Recorded source split cleared for %s.', line.product_id.display_name))
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_dvz_set_source_split(self):
        self.ensure_one()
        self._dvz_require_source_manager()
        self.check_access('write')
        if self.display_type or self.product_id.type != 'consu':
            raise UserError(_('Source splits are only applicable to physical products.'))
        action = self.env['ir.actions.actions']._for_xml_id(
            'dvz_sale_supply_report.action_dvz_sale_supply_source_wizard')
        action['context'] = dict(self.env.context, default_sale_line_id=self.id)
        return action

    def action_dvz_open_export(self):
        self.check_access('read')
        if self:
            # A selected report row chooses its SO; all sibling product lines
            # are exported for that order.
            return self.order_id.action_dvz_supply_export()
        action = self.env['ir.actions.actions']._for_xml_id(
            'dvz_sale_supply_report.action_dvz_sale_supply_export')
        context = dict(self.env.context)
        for name in ('default_scope', 'default_sale_line_ids', 'default_product_ids', 'default_order_ids'):
            context.pop(name, None)
        context.update(active_model='sale.order', active_ids=[], active_id=False)
        action['context'] = context
        return action

    def action_dvz_open_order(self):
        self.ensure_one()
        self.order_id.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': self.order_id.name,
                'res_model': 'sale.order', 'res_id': self.order_id.id,
                'view_mode': 'form', 'target': 'current'}
