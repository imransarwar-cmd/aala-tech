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
        lead = self.opportunity_id.exists()
        if not lead:
            raise UserError(
                "This quotation isn't linked to an Opportunity that "
                "still exists, so there's no Project Lines/Quotation "
                "Info data to print from. The linked Opportunity may "
                "have been deleted. Print from the Opportunity itself "
                "instead, or link a valid one via the 'Opportunity' "
                "field first."
            )
        report = self.env.ref("dvz_crm_ext.action_report_crm_lead_quotation")
        return report.report_action(lead)


class IrActionsReport(models.Model):
    """Makes the Excel-style quotation report work when triggered from
    the Quotation (sale.order) form's own native Print menu - see
    action_report_crm_lead_quotation_so in
    report/crm_lead_quotation_report.xml, which is the sale.order-bound
    copy of the same report. That menu passes the CURRENT form's own
    record ids straight through, but this report's template only
    understands crm.lead fields (Project Lines, Quotation Info, etc.),
    which don't exist on sale.order - so for this ONE specific action
    (checked by report_name + model below), redirect those sale.order
    ids to each order's linked Opportunity before rendering. Every
    other report in the system, including the crm.lead-bound copy of
    this same template, is completely unaffected."""
    _inherit = "ir.actions.report"

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        if (
            self.report_name == "dvz_crm_ext.report_crm_lead_quotation_document"
            and self.model == "sale.order"
            and res_ids
        ):
            orders = self.env["sale.order"].browse(res_ids).exists()
            leads = orders.mapped("opportunity_id").exists()
            if not leads:
                raise UserError(
                    "None of the selected quotation(s) are linked to an "
                    "Opportunity that still exists, so there's no "
                    "Project Lines/Quotation Info data to print from. "
                    "The linked Opportunity may have been deleted. "
                    "Print from the Opportunity itself instead, or link "
                    "a valid one via the 'Opportunity' field first."
                )
            res_ids = leads.ids
        return super()._render_qweb_pdf_prepare_streams(
            report_ref, data, res_ids=res_ids,
        )


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
