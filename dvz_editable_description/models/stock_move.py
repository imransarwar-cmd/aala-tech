# -*- coding: utf-8 -*-
from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def write(self, vals):
        """description_picking (confirmed real field on stock.move) is
        written directly via SQL, bypassing whichever internal done-move
        check would otherwise block it, while every other field in the
        same write() call still goes through Odoo's normal, fully-
        protected write path unchanged."""
        if "description_picking" in vals:
            new_desc = vals.pop("description_picking")
            if self:
                self.env.cr.execute(
                    "UPDATE stock_move SET description_picking = %s WHERE id IN %s",
                    (new_desc, tuple(self.ids)),
                )
                self.invalidate_recordset(fields=["description_picking"])
        if vals:
            return super().write(vals)
        return True
