# -*- coding: utf-8 -*-
from odoo import api, fields, models

STATUS_SELECTION = [
    ("ongoing", "Ongoing"),
    ("completed", "Completed"),
]


class CrmLead(models.Model):
    _inherit = "crm.lead"

    # Customer already exists natively as partner_id - not duplicated.
    dvz_project = fields.Many2one("project.project", string="Project")
    dvz_system_id = fields.Many2one(
        "system.master", string="System",
        help="Header-level default System, used on the Kanban quick-"
             "create card. The Project Lines tab below can still record "
             "a different System per individual line if needed.",
    )
    dvz_status = fields.Selection(STATUS_SELECTION, string="Status", default="ongoing")
    dvz_line_ids = fields.One2many(
        "crm.lead.line", "lead_id", string="System/Activity Lines",
    )

    dvz_amount_untaxed = fields.Float(
        string="Untaxed Amount", compute="_compute_dvz_amounts", store=True,
    )
    dvz_amount_tax = fields.Float(
        string="Taxes", compute="_compute_dvz_amounts", store=True,
    )
    dvz_amount_total = fields.Float(
        string="Total", compute="_compute_dvz_amounts", store=True,
    )

    @api.depends(
        "dvz_line_ids.quantity", "dvz_line_ids.price_unit",
        "dvz_line_ids.tax_ids", "dvz_line_ids.product_id",
    )
    def _compute_dvz_amounts(self):
        for lead in self:
            untaxed = 0.0
            tax_amount = 0.0
            currency = lead.env.company.currency_id
            for line in lead.dvz_line_ids:
                if not line.product_id:
                    continue
                # Uses Odoo's own tax engine (the same one sale.order.line
                # relies on) rather than a naive percentage sum, so
                # price-included taxes, tax groups, and rounding all
                # behave the same way they would on a real quotation.
                taxes_res = line.tax_ids.compute_all(
                    line.price_unit,
                    currency=currency,
                    quantity=line.quantity,
                    product=line.product_id,
                    partner=lead.partner_id,
                )
                untaxed += taxes_res["total_excluded"]
                tax_amount += taxes_res["total_included"] - taxes_res["total_excluded"]
            lead.dvz_amount_untaxed = untaxed
            lead.dvz_amount_tax = tax_amount
            lead.dvz_amount_total = untaxed + tax_amount

    def _dvz_build_order_line_commands(self):
        """Build order_line create-commands from every dvz_line_ids row
        that has a product set - shared by both the "New Quotation"
        button (below) and sale.order's own create() override, so the
        exact same logic runs regardless of which path actually creates
        the quotation.
        """
        self.ensure_one()
        line_vals = []
        for lead_line in self.dvz_line_ids:
            if not lead_line.product_id:
                continue
            line_vals.append((0, 0, {
                "product_id": lead_line.product_id.id,
                "name": lead_line.name or lead_line.product_id.name,
                "product_uom_qty": lead_line.quantity or 1.0,
                "price_unit": lead_line.price_unit or lead_line.product_id.list_price,
                "tax_ids": [(6, 0, lead_line.tax_ids.ids)],
            }))
        return line_vals

    def action_sale_quotations_new(self):
        """Extends the real "New Quotation" button (confirmed method
        name from Odoo core's sale_crm module) so the new quotation form
        opens with order_line already pre-filled from this lead's
        Project Lines table - visible immediately, before the user even
        saves the form, rather than only appearing after save (which is
        what the sale.order create() override alone would give)."""
        action = super().action_sale_quotations_new()
        order_lines = self._dvz_build_order_line_commands()
        if order_lines and isinstance(action, dict):
            action.setdefault("context", {})
            if isinstance(action["context"], dict):
                action["context"]["default_order_line"] = order_lines
        return action
