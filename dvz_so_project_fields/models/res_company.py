# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    dvz_show_project_fields = fields.Boolean(
        string="Show Project Fields on Quotations",
        default=True,
        help="Controls whether the Sales Engineer/Project/Area/Division/"
             "System/Brand/Status section is shown on the Quotation and "
             "Sale Order form. Toggle off to hide the whole section "
             "without deleting any data already entered in it.",
    )
