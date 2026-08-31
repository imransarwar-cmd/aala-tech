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
    presales_id = fields.Many2one("hr.employee", string="Presales")
    inquiry_date = fields.Date(string="Inquiry")
    due_date = fields.Date(string="Completion / Due Date")
    est_closing_date = fields.Date(string="Est. Closing")

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
