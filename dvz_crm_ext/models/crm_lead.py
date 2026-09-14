# -*- coding: utf-8 -*-
from odoo import api, fields, models

STATUS_SELECTION = [
    ("ongoing", "Ongoing"),
    ("completed", "Completed"),
]


class CrmLead(models.Model):
    _inherit = "crm.lead"

    system_id = fields.Many2one("system.master", string="System")
    activity = fields.Char(string="Activity")
    sales_id = fields.Many2one("hr.employee", string="Sales")
    # From the legacy tracking spreadsheet: Brand/Area as dropdowns
    # (dvz.brand / dvz.area, defined in dvz_master_data.py), plus two
    # plain fields that don't need a dropdown.
    brand_id = fields.Many2one("dvz.brand", string="Brand")
    area_id = fields.Many2one("dvz.area", string="Area")
    po_ref = fields.Char(string="PO - Ref #")
    remarks = fields.Text(string="Remarks")
    # Presales is no longer manually picked: it always mirrors the
    # Salesperson (user_id) shown at the top of the form, via the
    # matching hr.employee record for that user. Kept as a stored
    # Many2one (not a plain related char) so existing reports/filters
    # that group or search on presales_id keep working unchanged.
    presales_id = fields.Many2one(
        "hr.employee", string="Presales",
        compute="_compute_presales_id", store=True, readonly=True,
        help="Automatically set to the Salesperson's employee record - "
             "no longer manually selectable.",
    )
    inquiry_date = fields.Date(string="Inquiry")
    due_date = fields.Date(string="Due Date")
    est_closing_date = fields.Date(string="Est. Closing")

    contact_email_from = fields.Char(string="Contact Email")
    contact_phone = fields.Char(string="Contact Phone")

    @api.onchange("customer_contact_id")
    def _onchange_dvz_customer_contact_id(self):
        """Auto-fetch Email/Phone from the selected contact into their
        own dedicated fields (kept separate from email_from/phone)."""
        for lead in self:
            contact = lead.customer_contact_id
            if not contact:
                lead.contact_email_from = False
                lead.contact_phone = False
                continue
            lead.contact_email_from = contact.email or False
            lead.contact_phone = contact.phone or False

    # Customer already exists natively as partner_id - a view-level
    # domain restricts it to actual customers (see views/crm_lead_views.xml).
    # This new field lets a specific person at that customer's company be
    # picked separately - e.g. Customer = "Company A" (which has 4
    # contacts under it) shows exactly those 4 in this field's dropdown.
    customer_contact_id = fields.Many2one(
        "res.partner", string="Customer's Contact",
        domain="[('parent_id', '=', partner_id)]",
        help="A specific person at the selected Customer's company - "
             "only that company's own contacts are listed here. "
             "Selecting one auto-fills the Email and Phone fields.",
    )
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
    dvz_margin_total = fields.Float(
        string="Total Margin", compute="_compute_dvz_amounts", store=True,
        help="Sum of every line's (Total Price - Total Cost) - the actual "
             "profit amount baked in via each line's Profit %age.",
    )

    # --- Fields for the Excel-style quotation PDF (see
    # report/crm_lead_quotation_report.xml). Kept optional/manual since
    # this information doesn't otherwise exist on crm.lead. ---
    quotation_no = fields.Char(string="Quotation No.")
    quotation_title = fields.Char(
        string="Quotation Title",
        help="Short project/product title shown at the top of the "
             "quotation PDF, e.g. 'Honeywell Trend Thermostats'.",
    )
    quotation_site = fields.Char(
        string="Quotation Site",
        help="Site/building shown under 'for' on the quotation PDF, e.g. "
             "'Al-Kayan Business Park, Riyadh'.",
    )
    estimation_engineer_id = fields.Many2one(
        "hr.employee", string="Estimation Engineer",
        help="Shown as the left-hand signature on the quotation PDF.",
    )
    validity = fields.Char(string="Validity", default="4 weeks")
    payment_terms = fields.Char(string="Payment Terms", default="100% advance")
    delivery_terms = fields.Char(string="Delivery Terms", default="06 - 09 Weeks")
    bank_details = fields.Text(
        string="Bank Account",
        default="Aala Tech Company Ltd, SAB - Saudi Awwal Bank, "
                "IBAN SA63 4500 0000 2214 7957 9001",
    )
    quotation_intro = fields.Text(
        string="Quotation Intro",
        default="Thank you for considering Aala Tech Company for your "
                "project. Offer summary is as follows:",
    )
    quotation_outro = fields.Text(
        string="Quotation Closing Note",
        default="We hope our proposal will meet your requirements but "
                "feel free to contact us for any clarifications.",
    )
    quotation_client_logo = fields.Image(
        string="Client/Product Logo", max_width=1024, max_height=1024,
        help="Optional - e.g. the manufacturer's logo (Honeywell, etc). "
             "Shown on the cover page next to the Aala Tech logo, which "
             "is always included automatically.",
    )

    @api.depends("user_id")
    def _compute_presales_id(self):
        """Presales always mirrors the Salesperson (user_id): looks up
        the hr.employee record linked to that user rather than letting
        anyone pick a different employee by hand."""
        for lead in self:
            lead.presales_id = lead._dvz_employee_for_user(lead.user_id)

    def _dvz_employee_for_user(self, user):
        """hr.employee record linked to the given res.users, or an empty
        recordset if there isn't one / no user is set."""
        if not user:
            return self.env["hr.employee"]
        return self.env["hr.employee"].search(
            [("user_id", "=", user.id)], limit=1,
        )

    @api.onchange("partner_id")
    def _onchange_dvz_customer_contact_domain(self):
        """Keep Customer's Contact consistent with Customer: drop it if
        it no longer belongs to the newly selected company, and
        auto-select it when the customer itself has no separate
        contacts (i.e. the customer record IS the contact)."""
        for lead in self:
            if not lead.partner_id:
                lead.customer_contact_id = False
                continue
            company = lead.partner_id.commercial_partner_id
            if (
                lead.customer_contact_id
                and lead.customer_contact_id.commercial_partner_id != company
            ):
                lead.customer_contact_id = False
            if not lead.customer_contact_id and not lead.partner_id.child_ids:
                lead.customer_contact_id = lead.partner_id



    @api.depends(
        "dvz_line_ids.quantity", "dvz_line_ids.price_unit",
        "dvz_line_ids.tax_ids", "dvz_line_ids.product_id",
        "dvz_line_ids.amount", "dvz_line_ids.total_cost",
    )
    def _compute_dvz_amounts(self):
        for lead in self:
            untaxed = 0.0
            tax_amount = 0.0
            margin_total = 0.0
            currency = lead.env.company.currency_id
            for line in lead.dvz_line_ids:
                margin_total += (line.amount or 0.0) - (line.total_cost or 0.0)
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
            lead.dvz_margin_total = margin_total

    def _dvz_get_quotation_defaults(self):
        """Every sale.order field value derived from this lead, in one
        place - used to (a) pre-fill the "New Quotation" popup's context
        when it opens a blank form, (b) directly patch an already-
        created order if the native action creates one server-side
        immediately instead (context defaults only affect an unsaved
        NEW record, so they'd silently do nothing in that case), and
        (c) sale.order's own create() override, for any other creation
        path (API, imports, etc). Single source of truth so these three
        callers can't drift out of sync."""
        self.ensure_one()
        defaults = {}
        if self.dvz_project:
            defaults["project"] = self.dvz_project.name
        if self.dvz_status:
            defaults["dvz_status"] = self.dvz_status
        if self.brand_id:
            defaults["brand_id"] = self.brand_id.id
        if self.area_id:
            defaults["area_id"] = self.area_id.id
        if self.po_ref:
            defaults["po_ref"] = self.po_ref
        if self.remarks:
            defaults["remarks"] = self.remarks
        if self.priority:
            defaults["priority"] = self.priority
        if self.estimation_engineer_id:
            defaults["estimation_engineer_id"] = self.estimation_engineer_id.id
        if self.quotation_client_logo:
            defaults["quotation_client_logo"] = self.quotation_client_logo
        first_line = self.dvz_line_ids[:1]
        if first_line:
            if first_line.system_id:
                defaults["system"] = first_line.system_id.id
            if first_line.sales_id:
                defaults["dvz_sales_engineer_id"] = first_line.sales_id.id
        return defaults

    def _dvz_build_order_line_commands(self):
        """Build order_line create-commands from every dvz_line_ids row
        that has a product set - shared by both the "New Quotation"
        button (below) and sale.order's own create() override, so the
        exact same logic runs regardless of which path actually creates
        the quotation. Carries the full cost breakdown (Code, List
        Price, Discount, Freight, Exchange Rate, Profit%) onto the real
        sale.order.line too (see SaleOrderLine in sale_order.py) rather
        than leaving it behind on the crm.lead.line.
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
                "code": lead_line.code,
                "list_price": lead_line.list_price,
                "discount": lead_line.discount,
                "freight_percent": lead_line.freight_percent,
                "exchange_rate": lead_line.exchange_rate,
                "profit_percent": lead_line.profit_percent,
            }))
        return line_vals

    def action_sale_quotations_new(self):
        """Extends the real "New Quotation" button (confirmed method
        name from Odoo core's sale_crm module). Handles BOTH possible
        native behaviors defensively:
        - If it opens a blank/unsaved quotation form (target=new, no
          res_id yet): merge our defaults into the action's context as
          default_<field> entries, so the form shows them pre-filled.
        - If it creates the order server-side immediately and returns
          an action pointing at that existing res_id: context defaults
          do nothing for an existing record, so write() the values onto
          it directly instead - this is what was silently failing
          before (only the sale.order.create() override was firing,
          and only for fields it was told about at creation time).
        Either way, only ever fills fields that are still empty - never
        overwrites something already set on the order.
        """
        action = super().action_sale_quotations_new()
        order_lines = self._dvz_build_order_line_commands()
        defaults = self._dvz_get_quotation_defaults()

        if isinstance(action, dict):
            res_id = action.get("res_id")
            if res_id:
                order = self.env["sale.order"].browse(res_id)
                if order.exists():
                    write_vals = {
                        field: value for field, value in defaults.items()
                        if not order[field]
                    }
                    if order_lines and not order.order_line:
                        write_vals["order_line"] = order_lines
                    if write_vals:
                        order.write(write_vals)
            else:
                action.setdefault("context", {})
                if isinstance(action["context"], dict):
                    for field, value in defaults.items():
                        action["context"]["default_%s" % field] = value
                    if order_lines:
                        action["context"]["default_order_line"] = order_lines
        return action
