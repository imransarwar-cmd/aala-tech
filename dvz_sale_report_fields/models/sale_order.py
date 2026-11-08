# -*- coding: utf-8 -*-
from odoo import api, fields, models

STATUS_SELECTION = [
    ("ongoing", "Ongoing"),
    ("completed", "Completed"),
]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # NOTE:
    # - 'system' (Many2one -> system.master) and 'project' (Char) already
    #   exist on sale.order via aala_rest_api.
    # - 'dvz_division_id' is intentionally kept as a legacy Many2one field.
    #   The new visible fields are Many2many. Keeping the old fields avoids
    #   losing existing data and preserves compatibility with older code/API.

    dvz_sales_engineer_id = fields.Many2one(
        "hr.employee",
        string="Sales Engineer",
        help="The employee responsible for the technical/project side "
             "of this order - distinct from Salesperson.",
    )
    dvz_customer_name = fields.Char(
        string="Customer Name",
        compute="_compute_dvz_customer_name",
        store=True,
        help="Stored copy of the customer's name, for easy filtering/"
             "grouping in list views and reports without needing to open "
             "the linked contact record.",
    )
    dvz_area = fields.Char(string="Area")

    # Legacy field retained so all existing records stay intact.
    dvz_division_id = fields.Many2one("division.master", string="Division (Legacy)")

    # New multi-selection fields used in the UI/reporting.
    dvz_division_ids = fields.Many2many(
        "division.master",
        "sale_order_dvz_division_rel",
        "order_id",
        "division_id",
        string="Division",
        help="Select one or more divisions for this Sale Order.",
    )
    dvz_system_ids = fields.Many2many(
        "system.master",
        "sale_order_dvz_system_rel",
        "order_id",
        "system_id",
        string="System",
        help="Systems are filtered according to the selected divisions.",
    )

    # product.brand already exists as a full master-data model via
    # aala_rest_api - link to it rather than duplicating it as text.
    dvz_brand_id = fields.Many2one("product.brand", string="Brand")
    dvz_status = fields.Selection(STATUS_SELECTION, string="Status", default="ongoing")
    dvz_year = fields.Char(
        string="Year",
        compute="_compute_dvz_year",
        store=True,
        help="Year of the order date, stored for easy filtering/grouping "
             "and to match the Year column in the Sales Report format.",
    )

    @api.depends("partner_id", "partner_id.name")
    def _compute_dvz_customer_name(self):
        for order in self:
            order.dvz_customer_name = order.partner_id.name or ""

    @api.depends("date_order")
    def _compute_dvz_year(self):
        for order in self:
            order.dvz_year = str(order.date_order.year) if order.date_order else ""

    @api.onchange("dvz_division_ids")
    def _onchange_dvz_division_ids(self):
        """Remove systems that no longer belong to any selected division."""
        for order in self:
            if not order.dvz_division_ids:
                order.dvz_system_ids = [(5, 0, 0)]
                continue
            valid_systems = order.dvz_system_ids.filtered(
                lambda system: system.division in order.dvz_division_ids
            )
            if valid_systems != order.dvz_system_ids:
                order.dvz_system_ids = [(6, 0, valid_systems.ids)]

    def _sync_legacy_selection(self):
        """Keep old single-value fields usable by existing integrations.

        The first selected Division/System is mirrored to the old Many2one
        fields. The complete selection always remains in the Many2many fields.
        """
        for order in self:
            vals = {
                "dvz_division_id": order.dvz_division_ids[:1].id or False,
                "system": order.dvz_system_ids[:1].id or False,
            }
            super(SaleOrder, order).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order, vals in zip(orders, vals_list):
            # Compatibility for records created by older code that still
            # supplies only the legacy Many2one fields.
            extra_vals = {}
            if "dvz_division_ids" not in vals and order.dvz_division_id:
                extra_vals["dvz_division_ids"] = [(4, order.dvz_division_id.id)]
            if "dvz_system_ids" not in vals and order.system:
                extra_vals["dvz_system_ids"] = [(4, order.system.id)]
                if order.system.division:
                    extra_vals.setdefault("dvz_division_ids", [])
                    extra_vals["dvz_division_ids"].append((4, order.system.division.id))
            if extra_vals:
                super(SaleOrder, order).write(extra_vals)
        orders._sync_legacy_selection()
        return orders

    def write(self, vals):
        result = super().write(vals)

        # Older integrations may still write only the legacy fields. In that
        # case, add those values to the Many2many selections instead of
        # discarding any existing multi-selection data.
        if "dvz_division_ids" not in vals and "dvz_division_id" in vals and vals.get("dvz_division_id"):
            super(SaleOrder, self).write({
                "dvz_division_ids": [(4, vals["dvz_division_id"])],
            })
        if "dvz_system_ids" not in vals and "system" in vals and vals.get("system"):
            system = self.env["system.master"].browse(vals["system"])
            add_vals = {"dvz_system_ids": [(4, system.id)]}
            if system.division:
                add_vals["dvz_division_ids"] = [(4, system.division.id)]
            super(SaleOrder, self).write(add_vals)

        if "dvz_division_ids" in vals or "dvz_system_ids" in vals:
            self._sync_legacy_selection()
        return result

    def init(self):
        """Backfill new Many2many relations from historical Many2one data.

        This is idempotent and therefore safe on module upgrade. Existing
        records are copied, never removed, so historical values are retained.
        """
        self.env.cr.execute("""
            INSERT INTO sale_order_dvz_division_rel (order_id, division_id)
            SELECT so.id, so.dvz_division_id
              FROM sale_order so
             WHERE so.dvz_division_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
        self.env.cr.execute("""
            INSERT INTO sale_order_dvz_system_rel (order_id, system_id)
            SELECT so.id, so.system
              FROM sale_order so
             WHERE so.system IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
        self.env.cr.execute("""
            INSERT INTO sale_order_dvz_division_rel (order_id, division_id)
            SELECT so.id, sm.division
              FROM sale_order so
              JOIN system_master sm ON sm.id = so.system
             WHERE so.system IS NOT NULL
               AND sm.division IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
