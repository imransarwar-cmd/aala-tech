# -*- coding: utf-8 -*-
from odoo import fields, models


class DvzSaleSystem(models.Model):
    """Master list of Systems (BMS, GRMS, LCS, Meters, FA, PA, CCTV, ACS,
    CBS, etc.) - kept as its own small model rather than a hardcoded
    Selection field, since the list is expected to grow. Manage entries
    via Sales > Configuration > Systems."""
    _name = "dvz.sale.system"
    _description = "Sale Order System"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
