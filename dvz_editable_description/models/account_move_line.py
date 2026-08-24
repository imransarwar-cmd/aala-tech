# -*- coding: utf-8 -*-
from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def write(self, vals):
        """Same SQL-bypass pattern as stock.move - only 'name'
        (Description) is exempted from the posted-invoice write
        protection; every other field keeps full protection."""
        if "name" in vals:
            new_name = vals.pop("name")
            if self:
                self.env.cr.execute(
                    "UPDATE account_move_line SET name = %s WHERE id IN %s",
                    (new_name, tuple(self.ids)),
                )
                self.invalidate_recordset(fields=["name"])
        if vals:
            return super().write(vals)
        return True
