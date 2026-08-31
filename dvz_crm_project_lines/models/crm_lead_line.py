# -*- coding: utf-8 -*-
from odoo import fields, models


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
    due_date = fields.Date(string="Completion / Due Date")
    est_closing_date = fields.Date(string="Est. Closing")

    # Product-line fields, mirroring sale.order.line so each row here can
    # become a real order line once a quotation is created from this lead.
    product_id = fields.Many2one("product.product", string="Product")
    name = fields.Text(string="Description")
    quantity = fields.Float(string="Qty", default=1.0)
    price_unit = fields.Float(string="Amount")
    tax_ids = fields.Many2many("account.tax", string="Tax")
