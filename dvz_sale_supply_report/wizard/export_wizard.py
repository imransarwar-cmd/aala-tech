"""Export every product line of explicitly selected sales orders."""

import base64
from datetime import datetime, time, timedelta

import pytz

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..report.xlsx_export import build_sale_supply_xlsx


MAX_EXPORT_LINES = 10000


class SaleSupplyExport(models.TransientModel):
    _name = "dvz.sale.supply.export"
    _description = "Sales Supply Excel Export"

    # Retained for transient records/cached clients during upgrade. Legacy
    # product/line filters never narrow the selected sales orders' details.
    scope = fields.Selection(
        [("filters", "Filter sales lines"), ("selected", "Selected sales lines")],
        default="filters", required=True,
    )
    sale_line_ids = fields.Many2many("sale.order.line", string="Selected Product Lines", readonly=True)
    selected_count = fields.Integer(compute="_compute_selected_count", string="Selected Lines")
    date_from = fields.Date(string="Order Date From")
    date_to = fields.Date(string="Order Date To")
    customer_id = fields.Many2one("res.partner", string="Customer")
    product_ids = fields.Many2many("product.product", string="Products")
    order_ids = fields.Many2many(
        "sale.order", string="Sales Orders", required=True,
        help="Select one or more sales orders. Every product line of each selected order is included.",
    )
    date_from_utc = fields.Char(compute="_compute_date_boundaries")
    date_to_utc = fields.Char(compute="_compute_date_boundaries")
    company_ids = fields.Many2many(
        "res.company", string="Companies", required=True,
        default=lambda self: self.env.companies,
        domain=lambda self: [("id", "in", self.env.companies.ids)],
    )
    include_quotations = fields.Boolean(string="Include Quotations")
    include_cancelled = fields.Boolean(string="Include Cancelled Orders")
    file_data = fields.Binary(string="Excel File", readonly=True, attachment=False)
    file_name = fields.Char(string="Filename", readonly=True)
    exported_count = fields.Integer(string="Exported Lines", readonly=True)

    @api.depends("sale_line_ids")
    def _compute_selected_count(self):
        for wizard in self:
            wizard.selected_count = len(wizard.sale_line_ids)

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        if "order_ids" not in field_names or values.get("order_ids"):
            return values
        active_model = self.env.context.get("active_model")
        selected_ids = set(self.env.context.get("active_ids") or [])
        if not selected_ids and self.env.context.get("active_id"):
            selected_ids = {self.env.context["active_id"]}
        orders = self.env["sale.order"]
        if active_model == "sale.order.line" and selected_ids:
            lines = self.env["sale.order.line"].browse(selected_ids).exists()
            if len(lines) != len(selected_ids):
                raise UserError(_("A selected sales line no longer exists. Refresh the list and select the lines again."))
            lines.check_access("read")
            orders = lines.order_id
        elif active_model == "sale.order" and selected_ids:
            orders = self.env["sale.order"].browse(selected_ids).exists()
            if len(orders) != len(selected_ids):
                raise UserError(_("A selected sales order no longer exists. Refresh and select the orders again."))
        if orders:
            orders.check_access("read")
            values["order_ids"] = [Command.set(orders.ids)]
            if "include_quotations" in field_names and any(order.state in ("draft", "sent") for order in orders):
                values["include_quotations"] = True
            if "include_cancelled" in field_names and any(order.state == "cancel" for order in orders):
                values["include_cancelled"] = True
        return values

    @api.constrains("order_ids")
    def _check_required_orders(self):
        for wizard in self:
            if not wizard.order_ids:
                raise ValidationError(_("Select at least one Sales Order. All its product lines will be included."))

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("The starting order date must be on or before the ending order date."))

    def _timezone(self):
        self.ensure_one()
        name = self.env.context.get("tz") or self.env.user.tz or "UTC"
        try:
            return pytz.timezone(name)
        except pytz.UnknownTimeZoneError:
            return pytz.UTC

    def _utc_midnight(self, day):
        """Use an exclusive next-day bound so the complete local end date counts."""
        local = self._timezone().localize(datetime.combine(day, time.min), is_dst=False)
        return local.astimezone(pytz.UTC).replace(tzinfo=None)

    @api.depends("date_from", "date_to")
    @api.depends_context("tz", "uid")
    def _compute_date_boundaries(self):
        for wizard in self:
            wizard.date_from_utc = fields.Datetime.to_string(wizard._utc_midnight(wizard.date_from)) if wizard.date_from else False
            wizard.date_to_utc = fields.Datetime.to_string(wizard._utc_midnight(wizard.date_to + timedelta(days=1))) if wizard.date_to else False

    def _get_report_lines(self):
        self.ensure_one()
        if not self.order_ids:
            # Also protect RPC calls and old transient records with an empty
            # M2M from exporting the whole database.
            raise UserError(_("Select at least one Sales Order. All its product lines will be included."))
        orders = self.order_ids.exists()
        if len(orders) != len(self.order_ids):
            raise UserError(_("A selected sales order no longer exists. Refresh and select the orders again."))
        orders.check_access("read")
        allowed_companies = self.env.companies
        if any(order.company_id not in allowed_companies for order in orders):
            raise AccessError(_("Some selected sales orders belong to a company that is not active for you."))
        # Date/customer/state filters only help find orders. Selected orders
        # define the export and every sibling product line must be included.
        lines = orders.order_line
        lines.check_access("read")
        lines = lines.filtered(lambda line: not line.display_type and not line.is_downpayment and line.product_id)
        if len(lines) > MAX_EXPORT_LINES:
            raise UserError(_("These sales orders exceed %s product lines. Export fewer sales orders at a time.", MAX_EXPORT_LINES))
        if not lines:
            raise UserError(_("The selected sales orders have no product lines to report."))
        return lines.sorted(key=lambda line: (line.order_id.date_order, line.order_id.id, line.sequence, line.id))

    def action_view_product_details(self):
        self.ensure_one()
        lines = self._get_report_lines()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "dvz_sale_supply_report.action_dvz_sale_supply_report")
        action["domain"] = [("id", "in", lines.ids)]
        action["context"] = dict(self.env.context, search_default_confirmed=0, search_default_group_order=1)
        action["target"] = "current"
        return action

    def _make_rows(self, lines):
        rows = []
        for line in lines:
            # Export a numeric quantity only.  An unclassified delivered source
            # is *not* proof that the stock quantity was zero; the separate
            # source-status field in the detailed form retains that warning.
            # 0 here means no confirmed stock-sourced delivery is recorded.
            stock_used = max(0.0, line.dvz_stock_used_qty or 0.0)
            rows.append({
                "order": line.order_id.name or "",
                "product": line.product_id.display_name or "",
                "ordered": line.product_uom_qty,
                "delivered": line.qty_delivered,
                "stock_used": stock_used,
            })
        return rows

    def action_export(self):
        self.ensure_one()
        self.check_access("write")
        lines = self._get_report_lines()
        timezone = self._timezone()
        generated = pytz.UTC.localize(fields.Datetime.now()).astimezone(timezone).replace(tzinfo=None)
        names = self.order_ids.mapped("name")
        order_names = ", ".join(names[:10])
        if len(names) > 10:
            order_names += _(" and %s more", len(names) - 10)
        scope_description = _("All product lines of sales orders: %s", order_names)
        contents = build_sale_supply_xlsx(self._make_rows(lines), {
            "generated_at": generated, "timezone": timezone.zone,
            "company_name": self.env.company.name, "scope": scope_description,
        })
        self.write({
            "file_data": base64.b64encode(contents),
            "file_name": "Sales_Supply_Report_%s.xlsx" % generated.strftime("%Y%m%d_%H%M%S"),
            "exported_count": len(lines),
        })
        return {
            "type": "ir.actions.act_window", "name": _("Download Sales Supply Excel"),
            "res_model": self._name, "res_id": self.id, "view_mode": "form",
            "views": [(self.env.ref("dvz_sale_supply_report.view_dvz_sale_supply_export_form").id, "form")],
            "target": "new",
        }
