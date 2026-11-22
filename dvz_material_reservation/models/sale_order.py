from odoo import models, _
from odoo.exceptions import AccessError, UserError
from ..policy import INTERNAL_TOKEN


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _dvz_reservation_project_values(self):
        """Use existing typed links only. Never match project names or create a project."""
        self.ensure_one()
        project = self.env['project.project']
        analytic = self.env['account.analytic.account']
        chosen = self.company_id.dvz_reservation_project_field_id
        names = [chosen.name] if chosen else ['project_id', 'analytic_account_id', 'project_ids']
        note = _('No unambiguous project link found. Stock is reserved for this SO/customer; set the project on the reservation or configure the existing SO field.')
        for name in names:
            field = self._fields.get(name)
            if not field or field.type not in ('many2one', 'many2many'):
                continue
            if field.comodel_name not in ('project.project', 'account.analytic.account'):
                continue
            record = self[name]
            if len(record) > 1:
                note = _('Multiple projects exist on the SO. No project was guessed; select the reservation project explicitly.')
                continue
            if not record:
                continue
            if field.comodel_name == 'project.project':
                project = record
            else:
                analytic = record
            note = _('Reused existing Sales Order field: %s', name)
            break
        # Optional integration with the user's existing, unmodified naming addon.
        origin_field = self.env['project.project']._fields.get('dvz_origin_sale_id')
        if not chosen and not project and not analytic and origin_field and origin_field.type == 'many2one' and origin_field.comodel_name == 'sale.order':
            matches = self.env['project.project'].search([
                ('dvz_origin_sale_id', '=', self.id),
                ('company_id', 'in', [False, self.company_id.id])], limit=2)
            if len(matches) == 1:
                project = matches
                note = _('Reused the existing project naming link (dvz_origin_sale_id).')
            elif len(matches) > 1:
                note = _('Several projects reference this SO. Select a reservation project explicitly.')
        if project and not analytic:
            for name in ('account_id', 'analytic_account_id'):
                field = project._fields.get(name)
                if field and field.type == 'many2one' and field.comodel_name == 'account.analytic.account':
                    analytic = project[name]
                    break
        values = {'project_link_note': note}
        # Copy an explicitly configured existing SO Char field into the
        # reservation as a reference; do not create or guess project records.
        reference_field = self.company_id.dvz_reservation_project_reference_field_id
        if reference_field and reference_field.model == 'sale.order' and reference_field.ttype == 'char':
            values['project_reference'] = self[reference_field.name] or False
        if project and (not project.company_id or project.company_id == self.company_id):
            values['project_id'] = project.id
        if analytic and (not analytic.company_id or analytic.company_id == self.company_id):
            values['analytic_account_id'] = analytic.id
        return values

    def _dvz_material_moves(self):
        self.ensure_one()
        moves = self.order_line.move_ids
        frontier = moves
        # Follow real upstream links for warehouse pick/pack/ship steps.
        # Receipts, returns, manufacturing and other-SO operations are not reserved.
        seen = moves
        while frontier:
            parents = frontier.move_orig_ids - seen
            if not parents:
                break
            seen |= parents
            frontier = parents
        return seen.filtered(lambda m: m.company_id == self.company_id
            and m.product_id.is_storable and m.location_id.usage == 'internal'
            and not m.origin_returned_move_id
            and m.picking_id
            and (not m.sale_line_id or m.sale_line_id.order_id == self))

    def _dvz_sync_material_reservations(self):
        """Private confirmation hook. No changes to SO fields/lines or quantities.

        Scoped sudo matches native sale-stock procurement: create/update only
        this accessible SO's reservation and its existing stock operations.
        """
        for order in self:
            if order.state != 'sale' or not order.company_id.dvz_auto_material_reservation:
                continue
            order.check_access('read')
            if not self.env.su and order.company_id not in self.env.companies:
                raise AccessError(_('The SO company is not allowed for this user.'))
            # Serialize document creation even if another tab confirms/synchronizes.
            order.flush_recordset()
            self.env.cr.execute('SELECT id FROM sale_order WHERE id = %s FOR UPDATE', [order.id])
            scoped_order = order.sudo().with_company(order.company_id)
            moves = scoped_order._dvz_material_moves()
            if not moves:
                continue
            docs = self.env['dvz.material.reservation'].sudo().with_company(order.company_id).with_context(
                _dvz_material_internal=INTERNAL_TOKEN)
            reservation = docs.search([('sale_order_id', '=', order.id)], limit=1)
            values = scoped_order._dvz_reservation_project_values()
            if not reservation:
                reservation = docs.create({
                    'source': 'sale', 'stage': 'active', 'sale_order_id': order.id,
                    'partner_id': order.partner_id.id,
                    'delivery_partner_id': order.partner_shipping_id.id,
                    'company_id': order.company_id.id, 'warehouse_id': order.warehouse_id.id,
                    **values,
                })
            elif (
                (not reservation.project_id and not reservation.analytic_account_id)
                or (not reservation.project_reference and values.get('project_reference'))
            ):
                update_values = {
                    key: value for key, value in values.items()
                    if (key == 'project_reference' and not reservation.project_reference)
                    or (key == 'project_id' and not reservation.project_id)
                    or (key == 'analytic_account_id' and not reservation.analytic_account_id)
                    or (key == 'project_link_note' and not reservation.project_link_note)
                }
                if update_values:
                    reservation.write(update_values)
            conflicting = moves.filtered(lambda m: m.dvz_reservation_id and m.dvz_reservation_id != reservation)
            if conflicting:
                raise UserError(_('Some stock operations already belong to another reservation. Resolve that link before confirming.'))
            newly_linked = moves - moves.filtered('dvz_reservation_id')
            newly_linked.with_context(
                _dvz_material_internal=INTERNAL_TOKEN).write({'dvz_reservation_id': reservation.id})
            open_moves = moves.filtered(lambda m: m.state not in ('draft', 'done', 'cancel') and not m.picked)
            before = {m.id: m.dvz_reserved_qty for m in open_moves}
            open_moves._action_assign()
            for move in open_moves:
                if move in newly_linked or move.dvz_reserved_qty != before[move.id]:
                    reservation.with_user(self.env.user).sudo()._log_event('reserve',
                        _('Automatic reservation / refresh for confirmed Sales Order %s.', order.name),
                        move, before[move.id], move.dvz_reserved_qty)
        return True

    def action_confirm(self):
        result = super().action_confirm()
        self._dvz_sync_material_reservations()
        return result



class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        result = super()._action_launch_stock_rule(previous_product_uom_qty=previous_product_uom_qty)
        # Handles newly added products on an already confirmed SO. Existing
        # limits are retained: increasing SO demand does not undo a release.
        self.order_id.filtered(lambda order: order.state == 'sale')._dvz_sync_material_reservations()
        return result
