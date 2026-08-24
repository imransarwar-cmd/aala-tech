# -*- coding: utf-8 -*-
from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_protected_fields(self):
        """Core's write() blocks changes to a fixed list of "protected"
        fields whenever the parent order is locked (see sale/models/
        sale_order_line.py: `if any(self.order_id.mapped('locked')) and
        any(f in values.keys() for f in protected_fields): ...`). This
        removes 'name' (the line's Description) from that list, so the
        description stays editable on confirmed/locked orders while every
        other protection (quantity, price, product, etc.) still applies
        exactly as before - only the description text is exempted.
        """
        protected = super()._get_protected_fields()
        return [f for f in protected if f != "name"]
