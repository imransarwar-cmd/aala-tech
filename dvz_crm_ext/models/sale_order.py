# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

# Same selection values as crm.lead's own native "priority" field, so a
# quotation created from an Opportunity carries the same meaning across.
PRIORITY_SELECTION = [
    ("0", "Low"),
    ("1", "Medium"),
    ("2", "High"),
    ("3", "Very High"),
]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # From the legacy tracking spreadsheet, mirroring the same fields
    # added to crm.lead (dvz_master_data.py / crm_lead.py) so a
    # quotation created from an Opportunity keeps this data instead of
    # losing it.
    brand_id = fields.Many2one("dvz.brand", string="Brand")
    area_id = fields.Many2one("dvz.area", string="Area")
    po_ref = fields.Char(string="PO - Ref #")
    remarks = fields.Text(string="Remarks")
    estimation_engineer_id = fields.Many2one(
        "hr.employee", string="Estimation Engineer",
    )
    quotation_client_logo = fields.Image(
        string="Client/Product Logo", max_width=1024, max_height=1024,
    )
    # Selection widget (plain dropdown) rather than crm.lead's star
    # rating, per request - still the same underlying values/meaning.
    priority = fields.Selection(
        PRIORITY_SELECTION, string="Priority", default="0",
    )

    def _dvz_build_order_lines_from_opportunity(self, lead):
        """Delegates to crm.lead's own _dvz_build_order_line_commands()
        (shared with the "New Quotation" button override), so both
        paths use the exact same logic instead of two copies that could
        drift out of sync."""
        return lead._dvz_build_order_line_commands()

    def _dvz_apply_opportunity_defaults(self, vals):
        """When a quotation is created from an Opportunity (via the
        "New Quotation" button, which sets opportunity_id through the
        sale_crm bridge module), pull matching values from that lead's
        header fields onto this order's fields, and build real order
        lines from every crm.lead.line row - but only for fields/lines
        the caller didn't already explicitly provide, so this never
        overwrites values someone typed on the quotation creation form.
        Field list itself comes from crm.lead's own
        _dvz_get_quotation_defaults() (single source of truth shared
        with the "New Quotation" button override) rather than being
        duplicated here.
        """
        opportunity_id = vals.get("opportunity_id")
        if not opportunity_id:
            return vals

        lead = self.env["crm.lead"].browse(opportunity_id)
        if not lead.exists():
            return vals

        for field, value in lead._dvz_get_quotation_defaults().items():
            if field not in vals:
                vals[field] = value

        if "order_line" not in vals:
            built_lines = self._dvz_build_order_lines_from_opportunity(lead)
            if built_lines:
                vals["order_line"] = built_lines

        return vals

    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]
        vals_list = [self._dvz_apply_opportunity_defaults(v) for v in vals_list]
        return super().create(vals_list)

    def action_print_dvz_quotation(self):
        """Prints the same Excel-style quotation report used on the
        Opportunity, sourced from this order's linked opportunity_id -
        the report's own template (crm_lead_quotation_report.xml) reads
        crm.lead fields (Project Lines, Quotation Info, etc.) that don't
        exist on sale.order itself, so there isn't a separate sale.order
        version of this report; this just re-opens the same one against
        the originating lead."""
        self.ensure_one()
        if not self.opportunity_id:
            raise UserError(
                "This quotation isn't linked to an Opportunity, so "
                "there's no Project Lines/Quotation Info data to print "
                "from. Print it from the Opportunity itself instead, or "
                "link one via the 'Opportunity' field first."
            )
        report = self.env.ref("dvz_crm_ext.action_report_crm_lead_quotation")
        return report.report_action(self.opportunity_id)


class SaleOrderLine(models.Model):
    """Extends the actual order line (not just crm.lead.line) with the
    same cost-breakdown columns, so the List Price/Discount/Freight/
    Profit%/Cost detail from the Opportunity's Project Lines survives
    onto the real Quotation lines instead of being lost the moment a
    quotation is created (order_line only has product/qty/price_unit
    natively - none of that breakdown)."""
    _inherit = "sale.order.line"

    code = fields.Char(string="Code")
    list_price = fields.Float(string="List Price")
    # Reuses the native "discount" field (already a %-based Float on
    # sale.order.line) instead of adding a second, competing one.
    freight_percent = fields.Float(string="Freight & Custom")
    exchange_rate = fields.Float(string="Exchange Rate", default=3.75)
    profit_percent = fields.Float(string="Profit %age")
    unit_cost = fields.Float(
        string="Unit Cost In SR", compute="_compute_dvz_costs", store=True,
    )
    total_cost = fields.Float(
        string="Total Cost In SR", compute="_compute_dvz_costs", store=True,
    )

    @api.depends(
        "product_uom_qty", "list_price", "discount", "freight_percent",
        "exchange_rate",
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
            line.total_cost = (line.product_uom_qty or 0.0) * cost
