# -*- coding: utf-8 -*-
from odoo import fields, models

STATUS_SELECTION = [
    ("ongoing", "Ongoing"),
    ("completed", "Completed"),
]


class CrmLead(models.Model):
    _inherit = "crm.lead"

    # Customer already exists natively as partner_id - not duplicated.
    dvz_project = fields.Char(string="Project")
    dvz_status = fields.Selection(STATUS_SELECTION, string="Status", default="ongoing")
    dvz_line_ids = fields.One2many(
        "crm.lead.line", "lead_id", string="System/Activity Lines",
    )
