# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    dvz_show_project_fields = fields.Boolean(
        related="company_id.dvz_show_project_fields",
        readonly=False,
        string="Show Project Fields on Quotations",
    )
