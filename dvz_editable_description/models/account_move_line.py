from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def write(self, vals):
        """Odoo blocks most edits to journal items once the parent invoice
        is posted, as a safeguard for accounting integrity - which is
        exactly right for amounts, accounts, taxes, etc. Description text
        doesn't affect any financial calculation though, so this carves
        out just the 'name' field: it's written directly via SQL,
        bypassing whichever internal posted-move check would otherwise
        block it, while every other field in the same write() call still
        goes through Odoo's normal, fully-protected write path unchanged.

        This applies to every account.move.line, including invoice lines
        created for down payments - down payment lines are ordinary
        account.move.line records, not a separate model, so no extra
        handling is needed for them specifically.

        Note: bypassing the ORM for this field means the change won't
        appear in the chatter/tracking log the way a normal field write
        would. Given the compliance caveat already discussed (ZATCA-
        submitted invoices should ideally not have their content changed
        after clearance), use this deliberately, not as a routine habit.
        """
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
