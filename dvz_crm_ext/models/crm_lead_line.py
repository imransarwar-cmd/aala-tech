# -*- coding: utf-8 -*-
import math

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

    # --- Columns matching the Excel quotation sheet, in the same order
    # and with the same names/formulas as columns A-M there. ---
    product_id = fields.Many2one("product.product", string="Product")
    code = fields.Char(string="Code")
    name = fields.Text(string="Description")
    quantity = fields.Float(string="Qty", default=1.0)

    # Cost side - Excel columns I, J, K, L, M.
    list_price = fields.Float(string="List Price")
    discount = fields.Float(
        string="Discount",
        help="Enter as a percentage, e.g. 55 for 55% - the Excel sheet "
             "stores the same value as a fraction (0.55) but the formula "
             "is identical.",
    )
    freight_percent = fields.Float(
        string="Freight & Custom",
        help="Enter as a percentage, e.g. 16 for 16%.",
    )
    exchange_rate = fields.Float(
        string="Exchange Rate", default=3.75,
        help="List Price currency -> SR rate. Defaults to 3.75 (USD/SAR), "
             "matching the constant used in the Excel sheet.",
    )
    unit_cost = fields.Float(
        string="Unit Cost In SR", compute="_compute_dvz_costs", store=True,
        help="= List Price x (1 - Discount%) x Exchange Rate x "
             "(1 + Freight & Custom%) - same formula as the Excel sheet's "
             "'Unit Cost In SR' column (L).",
    )
    total_cost = fields.Float(
        string="Total Cost In SR", compute="_compute_dvz_costs", store=True,
        help="= Qty x Unit Cost - matches column M.",
    )

    # Selling side - Excel columns H, E, F.
    profit_percent = fields.Float(
        string="Profit %age",
        help="Enter as a percentage, e.g. 50 for 50% - the margin baked "
             "into the selling price (column H in the Excel sheet).",
    )
    price_unit = fields.Float(
        string="Unit Price In SR", compute="_compute_dvz_costs", store=True,
        help="= ROUNDUP(Unit Cost / (1 - Profit%), 0) - rounded UP to the "
             "nearest whole riyal, exactly matching the Excel formula in "
             "column E (=ROUNDUP(L/(1-H),0)).",
    )
    amount = fields.Float(
        string="Total Price In SR", compute="_compute_dvz_costs", store=True,
        help="= Qty x Unit Price - matches column F, and order_line's own "
             "subtotal calculation.",
    )

    tax_ids = fields.Many2many(
        "account.tax", string="Taxes",
        help="Not shown on the Excel-style quotation printout (which "
             "applies a flat 15% VAT on the grand total instead) but kept "
             "here so quotations created from this line still carry the "
             "right tax when needed.",
    )

    # Kept for records created before this change; no longer shown/edited
    # on the line (Profit %age + the cost breakdown above replace it).
    margin_percent = fields.Float(string="Margin % (legacy)")
    margin_amount = fields.Float(string="Margin Amount (legacy)")

    @api.depends(
        "quantity", "list_price", "discount", "freight_percent",
        "exchange_rate", "profit_percent",
    )
    def _compute_dvz_costs(self):
        for line in self:
            cost = (
                (line.list_price or 0.0)
                * (1 - (line.discount or 0.0) / 100.0)
                * (line.exchange_rate or 0.0)
                * (1 + (line.freight_percent or 0.0) / 100.0)
            )
            line.unit_cost = cost
            line.total_cost = (line.quantity or 0.0) * cost

            profit_fraction = (line.profit_percent or 0.0) / 100.0
            if cost and profit_fraction < 1:
                price = math.ceil(cost / (1 - profit_fraction))
            elif cost:
                # A Profit% of 100+ would divide by zero/negative in the
                # Excel formula - fall back to plain cost instead of
                # erroring out.
                price = math.ceil(cost)
            else:
                price = 0.0
            line.price_unit = price
            line.amount = (line.quantity or 0.0) * price

    @api.onchange("product_id")
    def _onchange_dvz_product_id(self):
        for line in self:
            if line.product_id:
                line.code = line.product_id.default_code or line.code
                line.name = line.name or line.product_id.name
                # Auto-fetch the product's Cost (standard_price) as the
                # starting List Price - the same role List Price plays in
                # the Excel sheet (the base cost before discount/freight/
                # exchange are applied). Only overwrites if still 0 so it
                # doesn't clobber a value someone already typed in.
                if not line.list_price:
                    line.list_price = line.product_id.standard_price
                # Auto-fetch the product's Cost (standard_price) into
                # List Price - the same figure the Excel sheet's "List
                # Price" column feeds into the Unit Cost formula. Only
                # overwrites if empty/zero so it won't clobber a value
                # someone already typed in on this line.
                if not line.list_price and line.product_id.standard_price:
                    line.list_price = line.product_id.standard_price
