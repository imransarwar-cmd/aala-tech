# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    arabic_name = fields.Char("Arabic Name")
    cr_no = fields.Char("Cr No#")
    arabic_address = fields.Char("Arabic Address")
    arabic_address_s2 = fields.Char("Street 2")
    arabic_address_city = fields.Char("City")
    arabic_zip = fields.Char("Zip")


class ResCountry(models.Model):
    _inherit = 'res.country'

    arabic_name = fields.Char("Arabic Name")