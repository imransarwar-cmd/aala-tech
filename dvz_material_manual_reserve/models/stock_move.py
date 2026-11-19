from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StockMove(models.Model):
    _inherit = "stock.move"

    dvz_manual_request_line_id = fields.Many2one(
        "dvz.manual.reservation.request.line", string="Manual Reservation Line",
        readonly=True, index=True, copy=True, check_company=True, ondelete="restrict",
    )

    def _prepare_merge_moves_distinct_fields(self):
        return super()._prepare_merge_moves_distinct_fields() + ["dvz_manual_request_line_id"]

    @api.constrains("dvz_manual_request_line_id", "product_id", "company_id")
    def _check_manual_reservation_product(self):
        for move in self:
            line = move.dvz_manual_request_line_id
            if line and (line.product_id != move.product_id or line.company_id != move.company_id):
                raise ValidationError(_("A reservation stock move must match its request product and company."))

    def write(self, vals):
        if "dvz_manual_request_line_id" in vals and any(
            (move.dvz_manual_request_line_id.id or False) != (vals["dvz_manual_request_line_id"] or False)
            for move in self
        ):
            raise UserError(_("An existing stock move cannot be reassigned to another reservation request."))
        return super().write(vals)
