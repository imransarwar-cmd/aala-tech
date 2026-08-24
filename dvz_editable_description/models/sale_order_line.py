# -*- coding: utf-8 -*-
from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # NOTE: we deliberately reuse the native 'name' field (Description)
    # rather than adding a separate custom field. Confirmed from Odoo's
    # own source: `name = fields.Text(compute='_compute_name', store=True,
    # readonly=False, required=True, precompute=True)` - it's already
    # designed to be user-editable and stored; the only thing blocking
    # edits after confirmation is core's _get_protected_fields() write
    # guard below, not the field definition itself.

    def _get_protected_fields(self):
        """Core's write() blocks changes to a fixed list of "protected"
        fields whenever the parent order is locked. This removes 'name'
        from that list, so the description stays editable on confirmed/
        locked orders while every other protection (quantity, price,
        product, etc.) still applies exactly as before.
        """
        protected = super()._get_protected_fields()
        return [f for f in protected if f != "name"]

    def write(self, vals):
        res = super().write(vals)
        if "name" in vals:
            # Push the updated description onto any delivery (stock.move)
            # and invoice line already generated from this line, so
            # editing it after confirmation keeps everything in sync
            # rather than leaving the delivery/invoice with stale text.
            move_ids = self.mapped("move_ids").ids
            if move_ids:
                self.env.cr.execute(
                    "UPDATE stock_move SET description_picking = %s WHERE id IN %s",
                    (vals["name"], tuple(move_ids)),
                )
                self.env["stock.move"].invalidate_model(fields=["description_picking"])
            invoice_line_ids = self.mapped("invoice_lines").ids
            if invoice_line_ids:
                self.env.cr.execute(
                    "UPDATE account_move_line SET name = %s WHERE id IN %s",
                    (vals["name"], tuple(invoice_line_ids)),
                )
                self.env["account.move.line"].invalidate_model(fields=["name"])
        return res

    def _prepare_procurement_values(self):
        """Confirmed real signature from a live traceback in this v19
        build: called as line._prepare_procurement_values() with no
        arguments at all (differs from the group_id=False signature seen
        in older Odoo versions/forum posts). Ensures the delivery move
        created from this line starts with the line's current
        description, since relying on core's own automatic sync was not
        reliable in this setup."""
        vals = super()._prepare_procurement_values()
        if self.name:
            vals["description_picking"] = self.name
        return vals
# -*- coding: utf-8 -*-
from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # NOTE: we deliberately reuse the native 'name' field (Description)
    # rather than adding a separate custom field. Confirmed from Odoo's
    # own source: `name = fields.Text(compute='_compute_name', store=True,
    # readonly=False, required=True, precompute=True)` - it's already
    # designed to be user-editable and stored; the only thing blocking
    # edits after confirmation is core's _get_protected_fields() write
    # guard below, not the field definition itself.

    def _get_protected_fields(self):
        """Core's write() blocks changes to a fixed list of "protected"
        fields whenever the parent order is locked. This removes 'name'
        from that list, so the description stays editable on confirmed/
        locked orders while every other protection (quantity, price,
        product, etc.) still applies exactly as before.
        """
        protected = super()._get_protected_fields()
        return [f for f in protected if f != "name"]

    def write(self, vals):
        res = super().write(vals)
        if "name" in vals:
            # Push the updated description onto any delivery (stock.move)
            # and invoice line already generated from this line, so
            # editing it after confirmation keeps everything in sync
            # rather than leaving the delivery/invoice with stale text.
            move_ids = self.mapped("move_ids").ids
            if move_ids:
                self.env.cr.execute(
                    "UPDATE stock_move SET description_picking = %s WHERE id IN %s",
                    (vals["name"], tuple(move_ids)),
                )
                self.env["stock.move"].invalidate_model(fields=["description_picking"])
            invoice_line_ids = self.mapped("invoice_lines").ids
            if invoice_line_ids:
                self.env.cr.execute(
                    "UPDATE account_move_line SET name = %s WHERE id IN %s",
                    (vals["name"], tuple(invoice_line_ids)),
                )
                self.env["account.move.line"].invalidate_model(fields=["name"])
        return res

    def _prepare_procurement_values(self):
        """Confirmed real signature from a live traceback in this v19
        build: called as line._prepare_procurement_values() with no
        arguments at all (differs from the group_id=False signature seen
        in older Odoo versions/forum posts). Ensures the delivery move
        created from this line starts with the line's current
        description, since relying on core's own automatic sync was not
        reliable in this setup."""
        vals = super()._prepare_procurement_values()
        if self.name:
            vals["description_picking"] = self.name
        return vals
