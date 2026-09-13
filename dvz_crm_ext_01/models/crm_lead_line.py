# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CrmLeadLine(models.Model):
    _name = "crm.lead.line"
    _description = "CRM Lead Line (System/Activity + Product tracking)"

    lead_id = fields.Many2one(
        "crm.lead", string="Lead/Opportunity",
        required=True, ondelete="cascade",
    )
    # Reuses the existing system.master model (from aala_rest_api) rather
    # than creating a second, competing "System" concept.
    system_id = fields.Many2one("system.master", string="System")
    activity = fields.Char(string="Activity")
    sales_id = fields.Many2one("hr.employee", string="Sales")
    presales_id = fields.Many2one("hr.employee", string="Presales")
    inquiry_date = fields.Date(string="Inquiry")
    due_date = fields.Date(string="Due Date")
    est_closing_date = fields.Date(string="Est. Closing")

    # Product-line fields, mirroring sale.order.line so each row here can
    # become a real order line once a quotation is created from this lead.
    product_id = fields.Many2one("product.product", string="Product")
    name = fields.Text(string="Description")
    quantity = fields.Float(string="Qty", default=1.0)
    price_unit = fields.Float(string="Unit Price")
    tax_ids = fields.Many2many("account.tax", string="Taxes")
    amount = fields.Float(
        string="Subtotal", compute="_compute_amount", store=True,
        help="Qty x Unit Price, before tax - matches order_line's own "
             "subtotal calculation, kept as a separate stored field from "
             "Unit Price itself.",
    )
    margin_percent = fields.Float(
        string="Margin %",
        help="Enter a margin percentage manually (e.g. 10 for 10%) - the "
             "Margin Amount field is then calculated automatically from "
             "this and the line's Subtotal.",
    )
    margin_amount = fields.Float(
        string="Margin Amount", compute="_compute_margin_amount", store=True,
        help="Subtotal x Margin % / 100 - calculated automatically from "
             "the Margin % you enter, shown as its own field so both the "
             "percentage and the resulting amount are visible together.",
    )

    @api.depends("quantity", "price_unit")
    def _compute_amount(self):
        for line in self:
            line.amount = (line.quantity or 0.0) * (line.price_unit or 0.0)

    @api.depends("amount", "margin_percent")
    def _compute_margin_amount(self):
        for line in self:
            line.margin_amount = (line.amount or 0.0) * (line.margin_percent or 0.0) / 100.0
