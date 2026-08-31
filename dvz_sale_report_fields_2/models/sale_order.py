# -*- coding: utf-8 -*-
from odoo import api, fields, models

STATUS_SELECTION = [
    ("ongoing", "Ongoing"),
    ("completed", "Completed"),
]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # NOTE: 'system' (Many2one to system.master) and 'project' (Char)
    # already exist on sale.order via aala_rest_api - not redefined here.
    # 'amount_untaxed' (Value without VAT) is native Odoo - not redefined.

    dvz_sales_engineer_id = fields.Many2one(
        "hr.employee",
        string="Sales Engineer",
        help="The employee responsible for the technical/project side "
             "of this order - distinct from Salesperson.",
    )
    dvz_customer_name = fields.Char(
        string="Customer Name",
        compute="_compute_dvz_customer_name",
        store=True,
        help="Stored copy of the customer's name, for easy filtering/"
             "grouping in list views and reports without needing to open "
             "the linked contact record.",
    )
    dvz_area = fields.Char(string="Area")
    # division.master already exists (via aala_rest_api) but was only
    # linked from system.master/product.brand, never directly from
    # sale.order - this adds that missing link.
    dvz_division_id = fields.Many2one("division.master", string="Division")
    # product.brand already exists as a full master-data model (image,
    # banner, description, division link) via aala_rest_api - linking to
    # it directly instead of adding a plain duplicate Char field.
    dvz_brand_id = fields.Many2one("product.brand", string="Brand")
    dvz_status = fields.Selection(STATUS_SELECTION, string="Status", default="ongoing")
    dvz_year = fields.Char(
        string="Year",
        compute="_compute_dvz_year",
        store=True,
        help="Year of the order date, stored for easy filtering/grouping "
             "and to match the Year column in the Sales Report format.",
    )

    @api.depends("partner_id", "partner_id.name")
    def _compute_dvz_customer_name(self):
        for order in self:
            order.dvz_customer_name = order.partner_id.name or ""

    @api.depends("date_order")
    def _compute_dvz_year(self):
        for order in self:
            order.dvz_year = str(order.date_order.year) if order.date_order else ""
