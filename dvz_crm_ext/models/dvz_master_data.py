# -*- coding: utf-8 -*-
from odoo import fields, models


class DvzBrand(models.Model):
    """Simple dropdown list of product/manufacturer brands (e.g. Trend,
    Netix) - matches the existing system.master pattern used for the
    'System' field rather than introducing a heavier product-brand
    concept the database doesn't already have."""
    _name = "dvz.brand"
    _description = "Quotation Brand"
    _order = "name"

    name = fields.Char(required=True)
    logo = fields.Image(
        string="Logo", max_width=1024, max_height=1024,
        help="Auto-used as the Client/Product Logo on the quotation PDF "
             "cover page whenever this Brand is selected on an "
             "Opportunity, unless a logo is uploaded directly on that "
             "Opportunity's Quotation Info tab (which always wins).",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "This brand already exists."),
    ]


class DvzArea(models.Model):
    """Simple dropdown list of sales areas/regions (e.g. Riyadh, Jeddah)."""
    _name = "dvz.area"
    _description = "Quotation Area"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "This area already exists."),
    ]


class DvzActivity(models.Model):
    """Simple, user-editable list of activity types (e.g. Site Visit,
    Call, Meeting) - replaces the earlier hardcoded Selection list on
    crm.lead's own Activity field, same pattern as Brand/Area above so
    it's managed from Configuration instead of needing a code change
    every time a new activity type comes up."""
    _name = "dvz.activity"
    _description = "Lead Activity Type"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "This activity type already exists."),
    ]
