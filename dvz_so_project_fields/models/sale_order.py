# -*- coding: utf-8 -*-
from odoo import api, fields, models

DIVISION_SELECTION = [
    ("bms", "BMS"),
    ("grms", "GRMS"),
    ("lcs", "LCS"),
    ("elv", "ELV"),
    ("maintenance", "Maintenance"),
    ("mep", "MEP"),
]

STATUS_SELECTION = [
    ("ongoing", "Ongoing"),
    ("completed", "Completed"),
]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    dvz_sales_engineer_id = fields.Many2one(
        "res.users",
        string="Sales Engineer",
        help="Distinct from Salesperson - the engineer responsible for "
             "the technical/project side of this order.",
    )
    dvz_customer_name = fields.Char(
        string="Customer Name",
        compute="_compute_dvz_customer_name",
        store=True,
        help="Stored copy of the customer's name, for easy filtering/"
             "grouping in list views and reports without needing to open "
             "the linked contact record.",
    )
    dvz_project_name = fields.Char(string="Project Name")
    dvz_area = fields.Char(string="Area")
    dvz_division = fields.Selection(DIVISION_SELECTION, string="Division")
    dvz_system_id = fields.Many2one("dvz.sale.system", string="System")
    dvz_brand = fields.Char(string="Brand")
    dvz_status = fields.Selection(STATUS_SELECTION, string="Status", default="ongoing")

    @api.depends("partner_id", "partner_id.name")
    def _compute_dvz_customer_name(self):
        for order in self:
            order.dvz_customer_name = order.partner_id.name or ""
