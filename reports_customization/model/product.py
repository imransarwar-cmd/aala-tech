# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class ProductTemplate(models.Model):
    _inherit = "product.template"

    system = fields.Char()
    division = fields.Char()
    categ_id = fields.Many2one('product.category', 'Brand')

class StockQuant(models.Model):
    _inherit = "stock.quant"

    unit_cost = fields.Float(related="product_id.standard_price")
    system = fields.Char(related="product_id.system")
    division = fields.Char(related="product_id.division")