# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _dvz_build_order_lines_from_opportunity(self, lead):
        """Build order_line commands from every crm.lead.line on the
        source lead, so each tracked System/Activity/Product row becomes
        a real Sale Order line - not just a single set of header
        defaults. Lines without a product are skipped (nothing to
        invoice), since a bare System/Activity row with no product isn't
        a valid order line on its own.
        """
        line_vals = []
        for lead_line in lead.dvz_line_ids:
            if not lead_line.product_id:
                continue
            line_vals.append((0, 0, {
                "product_id": lead_line.product_id.id,
                "name": lead_line.name or lead_line.product_id.name,
                "product_uom_qty": lead_line.quantity or 1.0,
                "price_unit": lead_line.price_unit or lead_line.product_id.list_price,
                "tax_id": [(6, 0, lead_line.tax_ids.ids)],
            }))
        return line_vals

    def _dvz_apply_opportunity_defaults(self, vals):
        """When a quotation is created from an Opportunity (via the
        "New Quotation" button, which sets opportunity_id through the
        sale_crm bridge module), pull matching values from that lead's
        header fields onto this order's fields, and build real order
        lines from every crm.lead.line row - but only for fields/lines
        the caller didn't already explicitly provide, so this never
        overwrites values someone typed on the quotation creation form.

        NOTE: System/Sales Engineer on the order are single-value fields,
        while a lead can have several lines - the FIRST line's System/
        Sales values populate those header fields; every line (with a
        product set) becomes its own order line regardless.
        """
        opportunity_id = vals.get("opportunity_id")
        if not opportunity_id:
            return vals

        lead = self.env["crm.lead"].browse(opportunity_id)
        if not lead.exists():
            return vals

        if "project" not in vals and lead.dvz_project:
            vals["project"] = lead.dvz_project
        if "dvz_status" not in vals and lead.dvz_status:
            vals["dvz_status"] = lead.dvz_status

        first_line = lead.dvz_line_ids[:1]
        if first_line:
            if "system" not in vals and first_line.system_id:
                vals["system"] = first_line.system_id.id
            if "dvz_sales_engineer_id" not in vals and first_line.sales_id:
                vals["dvz_sales_engineer_id"] = first_line.sales_id.id

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
