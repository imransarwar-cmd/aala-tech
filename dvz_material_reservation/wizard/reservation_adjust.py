from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from ..policy import release_target


class ReservationAdjust(models.TransientModel):
    _name = 'dvz.reservation.adjust'
    _description = 'Release or Set Material Reservation Target'
    _check_company_auto = True

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    mode = fields.Selection([('release', 'Release Quantity'), ('target', 'Set Total Reservation Target')],
                             required=True, default='release')
    release_all = fields.Boolean(string='Release all and stop automatic re-reservation', default=False,
        help='Sets the target to zero for every displayed operation, including currently unreserved shortages.')
    reason = fields.Char(required=True, string='Reason / Reference')
    line_ids = fields.One2many('dvz.reservation.adjust.line', 'wizard_id', string='Operations')

    def action_apply(self):
        self.ensure_one()
        self.env['dvz.material.reservation']._require_operator()
        self.check_access('write')
        if not (self.reason or '').strip():
            raise ValidationError(_('Enter a reason for the reservation change.'))
        if not self.line_ids:
            raise UserError(_('No operations selected.'))
        if len(self.line_ids.move_id) != len(self.line_ids):
            raise UserError(_('The same operation cannot appear twice in the adjustment.'))
        moves = self.line_ids.move_id
        if moves.company_id != self.company_id:
            raise UserError(_('All operations must belong to this wizard\'s company.'))
        moves.dvz_reservation_id._lock()
        moves._dvz_lock_rows()
        plans = []
        # Validate EVERY row before changing any stock. The RPC transaction
        # rolls back all changes if any core reservation operation fails.
        for line in self.line_ids:
            move = line.move_id
            move._dvz_assert_adjustable()
            if self.mode == 'release':
                if self.release_all:
                    target = 0
                elif line.quantity == 0:
                    continue
                else:
                    try:
                        target = release_target(move.quantity, line.quantity, move.product_uom.rounding)
                    except (TypeError, ValueError) as error:
                        raise ValidationError(str(error)) from error
            else:
                target = line.quantity
            target = move._dvz_validate_target(target)
            plans.append((move, target))
        if not plans:
            raise UserError(_('Enter a positive release quantity or select Release all.'))
        for move, target in plans:
            move._dvz_set_target(target, self.reason.strip(), self.mode)
        return {'type': 'ir.actions.act_window_close'}


class ReservationAdjustLine(models.TransientModel):
    _name = 'dvz.reservation.adjust.line'
    _description = 'Material Reservation Adjustment Line'

    wizard_id = fields.Many2one('dvz.reservation.adjust', required=True, ondelete='cascade')
    move_id = fields.Many2one('stock.move', required=True, readonly=True)
    product_id = fields.Many2one(related='move_id.product_id')
    reservation_id = fields.Many2one(related='move_id.dvz_reservation_id')
    picking_id = fields.Many2one(related='move_id.picking_id')
    uom_id = fields.Many2one(related='move_id.product_uom')
    demand_qty = fields.Float(related='move_id.product_uom_qty')
    reserved_qty = fields.Float(related='move_id.dvz_reserved_qty')
    target_qty = fields.Float(related='move_id.dvz_target_qty')
    quantity = fields.Float(string='Release Qty / New Total Target', required=True, digits='Product Unit')
