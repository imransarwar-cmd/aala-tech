import math

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


_WORKFLOW_TOKEN = object()
_WORKFLOW_CONTEXT = "dvz_manual_reservation_workflow"


class ManualReservationRequest(models.Model):
    _name = "dvz.manual.reservation.request"
    _description = "Manual Material Reservation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _check_company_auto = True

    name = fields.Char(default=lambda self: _("New"), required=True, readonly=True, copy=False, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    partner_id = fields.Many2one("res.partner", string="Customer", check_company=True, tracking=True)
    project_id = fields.Many2one("project.project", string="Project", check_company=True, tracking=True)
    sale_order_id = fields.Many2one(
        "sale.order", string="SO Reference", check_company=True, ondelete="restrict",
        domain="[('state', 'in', ['draft', 'sent']), ('company_id', '=', company_id)]",
        help="Optional quotation reference. This request neither confirms nor delivers the quotation.",
    )
    date = fields.Datetime(string="Scheduled Date", required=True, default=fields.Datetime.now)
    picking_type_id = fields.Many2one(
        "stock.picking.type", string="Delivery Operation", required=True, check_company=True,
        default=lambda self: self.env["stock.picking.type"].search([
            ("code", "=", "outgoing"), ("company_id", "=", self.env.company.id),
        ], limit=1),
        domain="[('code', '=', 'outgoing'), ('company_id', '=', company_id)]",
    )
    location_id = fields.Many2one(
        "stock.location", string="Source Location", required=True, check_company=True,
        compute="_compute_location_id", store=True, readonly=False, precompute=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [False, company_id])]",
    )
    line_ids = fields.One2many(
        "dvz.manual.reservation.request.line", "request_id", string="Materials", copy=True,
    )
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("cancel", "Cancelled")],
        default="draft", required=True, readonly=True, copy=False, tracking=True, index=True,
    )
    picking_id = fields.Many2one(
        "stock.picking", string="Initial Transfer", readonly=True, copy=False,
        check_company=True, ondelete="restrict",
    )
    picking_ids = fields.Many2many("stock.picking", compute="_compute_pickings", string="Transfers")
    picking_count = fields.Integer(compute="_compute_pickings")
    reservation_status = fields.Selection([
        ("draft", "Draft"), ("waiting", "Waiting for Stock"),
        ("partial", "Partially Reserved"), ("reserved", "Reserved"),
        ("delivered", "Delivered"), ("cancel", "Cancelled"),
    ], string="Reservation Status", compute="_compute_reservation_status", store=True, index=True)
    notes = fields.Text()
    line_revision = fields.Integer(default=0, readonly=True, copy=False)

    @api.depends("picking_type_id")
    def _compute_location_id(self):
        for request in self:
            request.location_id = (
                request.picking_type_id.default_location_src_id
                or request.picking_type_id.warehouse_id.lot_stock_id
            )

    @api.depends("picking_id", "line_ids.move_ids.picking_id")
    def _compute_pickings(self):
        for request in self:
            request.picking_ids = request.picking_id | request.line_ids.move_ids.picking_id
            request.picking_count = len(request.picking_ids)

    @api.depends(
        "state", "line_ids.requested_qty", "line_ids.reserved_qty", "line_ids.delivered_qty",
        "line_ids.remaining_qty", "line_ids.move_ids.state", "line_ids.product_uom_id.rounding",
    )
    def _compute_reservation_status(self):
        for request in self:
            lines = request.line_ids
            moves = lines.move_ids
            if request.state in ("draft", "cancel"):
                status = request.state
            elif moves and all(move.state == "cancel" for move in moves):
                status = "cancel"
            elif lines and all(float_compare(
                line.delivered_qty, line.requested_qty, precision_rounding=line.product_uom_id.rounding,
            ) >= 0 for line in lines):
                status = "delivered"
            elif lines and all(float_is_zero(
                line.remaining_qty, precision_rounding=line.product_uom_id.rounding,
            ) for line in lines) and any(line.reserved_qty for line in lines):
                status = "reserved"
            elif any(line.reserved_qty for line in lines):
                status = "partial"
            else:
                status = "waiting"
            request.reservation_status = status

    @api.onchange("project_id")
    def _onchange_project_id(self):
        if self.project_id.partner_id and not self.partner_id:
            self.partner_id = self.project_id.partner_id

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        if self.sale_order_id and not self.partner_id:
            self.partner_id = self.sale_order_id.partner_id

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.picking_type_id.company_id != self.company_id:
            self.picking_type_id = self.env["stock.picking.type"].search([
                ("code", "=", "outgoing"), ("company_id", "=", self.company_id.id),
            ], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            if vals.get("state", "draft") != "draft" or vals.get("picking_id"):
                raise UserError(_("Create a draft request, then use Confirm."))
            if {"picking_ids", "picking_count", "reservation_status", "line_revision"} & vals.keys():
                raise UserError(_("Transfer links and reservation status are calculated automatically."))
            company_id = vals.get("company_id") or self.default_get(["company_id"]).get("company_id")
            company = self.env["res.company"].browse(company_id)
            if company not in self.env.companies:
                raise AccessError(_("Select one of your active companies."))
            vals.update(company_id=company.id, state="draft", picking_id=False, line_revision=0)
            vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code(
                "dvz.manual.reservation.request"
            ) or _("New")
        protected_defaults = {
            "default_" + field for field in
            ("name", "state", "picking_id", "picking_ids", "picking_count", "reservation_status", "line_revision")
        }
        clean_context = {key: value for key, value in self.env.context.items() if key not in protected_defaults}
        return super(ManualReservationRequest, self.with_context(clean_context)).create(vals_list)

    def _lock_requests(self):
        if not self:
            return
        self.check_access("write")
        self.flush_recordset(["state", "picking_id", "line_revision"])
        self.env.cr.execute(
            "SELECT id FROM dvz_manual_reservation_request WHERE id IN %s ORDER BY id FOR UPDATE",
            [tuple(self.ids)],
        )
        self.invalidate_recordset()

    def _touch_line_revision(self):
        if self:
            # A parent-row change makes concurrent draft-line edits/confirmation
            # serialize (or retry) correctly under PostgreSQL REPEATABLE READ.
            self.flush_recordset(["line_revision"])
            self.env.cr.execute(
                "UPDATE dvz_manual_reservation_request SET line_revision = COALESCE(line_revision, 0) + 1 WHERE id IN %s",
                [tuple(self.ids)],
            )
            self.invalidate_recordset(["line_revision"])

    def write(self, vals):
        if self.env.context.get(_WORKFLOW_CONTEXT) is not _WORKFLOW_TOKEN:
            if {"state", "picking_id", "picking_ids", "picking_count", "reservation_status", "name", "line_revision"} & vals.keys():
                raise UserError(_("Use the reservation buttons to change its workflow."))
            if {"company_id", "partner_id", "project_id", "sale_order_id", "date",
                "picking_type_id", "location_id", "line_ids", "notes"} & vals.keys():
                self._lock_requests()
                if any(request.state != "draft" for request in self):
                    raise UserError(_("A confirmed or cancelled request cannot be edited. Create a new request instead."))
        return super().write(vals)

    def unlink(self):
        self._lock_requests()
        if any(request.state != "draft" or request.picking_id for request in self):
            raise UserError(_("Only draft requests without a transfer can be deleted."))
        return super().unlink()

    def _check_operator(self):
        if not self.env.user.has_group("stock.group_stock_user"):
            raise AccessError(_("Inventory access is required to manage reservations."))
        self.check_access("write")
        if any(request.company_id not in self.env.companies for request in self):
            raise AccessError(_("The request company is not one of your active companies."))

    def _validate_request(self):
        self.ensure_one()
        self._check_company()
        if not self.partner_id and not self.project_id:
            raise ValidationError(_("Select a customer or a project."))
        if not self.line_ids:
            raise ValidationError(_("Add at least one material."))
        if self.picking_type_id.code != "outgoing":
            raise ValidationError(_("Select a delivery operation."))
        if self.picking_type_id.company_id != self.company_id:
            raise ValidationError(_("The delivery operation belongs to another company."))
        if not self.location_id or self.location_id.usage != "internal":
            raise ValidationError(_("Select an internal source location."))
        if self.sale_order_id:
            if self.sale_order_id.state not in ("draft", "sent"):
                raise ValidationError(_("For a confirmed Sales Order, reserve its existing delivery instead."))
            if self.partner_id and (
                self.sale_order_id.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id
            ):
                raise ValidationError(_("The quotation reference belongs to another customer."))
        self.line_ids._validate_materials()

    def action_confirm(self):
        self.ensure_one()
        self._check_operator()
        self._lock_requests()
        if self.state == "confirmed":
            return True
        if self.state != "draft":
            raise UserError(_("Only a draft request can be confirmed."))
        self._validate_request()
        request = self.with_company(self.company_id)
        destination = (
            request.picking_type_id.default_location_dest_id
            or request.partner_id.property_stock_customer
            or self.env.ref("stock.stock_location_customers")
        )
        if destination.usage != "customer" or (
            destination.company_id and destination.company_id != self.company_id
        ):
            raise ValidationError(_("The destination must be a customer location for this company."))
        picking = request.env["stock.picking"].create({
            "company_id": request.company_id.id,
            "partner_id": request.partner_id.id or False,
            "picking_type_id": request.picking_type_id.id,
            "location_id": request.location_id.id,
            "location_dest_id": destination.id,
            "origin": request.name,
            "dvz_manual_project_id": request.project_id.id or False,
            "dvz_manual_so_id": request.sale_order_id.id or False,
        })
        moves = request.env["stock.move"].create([
            {
                "picking_id": picking.id,
                "product_id": line.product_id.id,
                "product_uom_qty": line.requested_qty,
                "product_uom": line.product_uom_id.id,
                "location_id": request.location_id.id,
                "location_dest_id": destination.id,
                "company_id": request.company_id.id,
                "date": request.date,
                "origin": request.name,
                "dvz_manual_request_line_id": line.id,
            }
            for line in request.line_ids
        ])
        # Odoo creates and manages its operation lines, lots and quant reservations.
        # This addon only creates demand moves and invokes the native stock workflow.
        moves._action_confirm(merge=False)
        picking.action_assign()
        request.with_context(**{_WORKFLOW_CONTEXT: _WORKFLOW_TOKEN}).write({
            "state": "confirmed", "picking_id": picking.id,
        })
        request.message_post(body=_("Reservation confirmed. Transfer: %s", picking.display_name))
        return True

    def _pending_pickings(self):
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(_("Confirm the request first."))
        owned = self.line_ids.move_ids
        pending = owned.filtered(lambda move:
            move.state not in ("draft", "cancel", "done")
            and move.location_id.usage == "internal"
            and move.location_dest_id.usage == "customer"
        )
        pickings = pending.picking_id
        for picking in pickings:
            if picking.move_ids - owned:
                raise UserError(_("This transfer contains lines outside the request. Manage it from its Transfer form."))
        return pickings, pending

    def action_reserve(self):
        self.ensure_one()
        self._check_operator()
        self._lock_requests()
        pickings, moves = self._pending_pickings()
        if not moves:
            raise UserError(_("There are no pending transfer lines to reserve."))
        pickings.with_company(self.company_id).action_assign()
        self.message_post(body=_("Stock availability checked using the native transfer workflow."))
        return True

    def action_unreserve(self):
        self.ensure_one()
        self._check_operator()
        self._lock_requests()
        pickings, moves = self._pending_pickings()
        if any(move.picked for move in moves):
            raise UserError(_("Some materials are marked Picked. Review the transfer before unreserving."))
        if pickings:
            pickings.with_company(self.company_id).do_unreserve()
            self.message_post(body=_("Pending reservations released. The transfer demand remains open."))
        return True

    def action_cancel(self):
        self.ensure_one()
        self._check_operator()
        self._lock_requests()
        if self.state == "cancel":
            return True
        if self.state == "confirmed":
            if any(move.state == "done" for move in self.line_ids.move_ids):
                raise UserError(_("This request has completed movements. Manage the remaining backorder from its transfer."))
            pickings, moves = self._pending_pickings()
            if any(move.picked for move in moves):
                raise UserError(_("Some materials are marked Picked. Review the transfer before cancelling."))
            pickings.with_company(self.company_id).action_cancel()
        self.with_context(**{_WORKFLOW_CONTEXT: _WORKFLOW_TOKEN}).write({"state": "cancel"})
        return True

    def action_view_pickings(self):
        self.ensure_one()
        self.check_access("read")
        action = {
            "type": "ir.actions.act_window", "name": _("Reservation Transfers"),
            "res_model": "stock.picking", "view_mode": "list,form",
            "domain": [("id", "in", self.picking_ids.ids)],
        }
        if len(self.picking_ids) == 1:
            action.update(view_mode="form", res_id=self.picking_ids.id)
        return action

    def action_view_report(self):
        self.ensure_one()
        self.check_access("read")
        action = self.env["ir.actions.actions"]._for_xml_id(
            "dvz_material_manual_reserve.action_manual_reservation_lines"
        )
        action["domain"] = [("request_id", "=", self.id)]
        action["context"] = {"create": False}
        return action


class ManualReservationRequestLine(models.Model):
    _name = "dvz.manual.reservation.request.line"
    _description = "Manual Material Reservation Line"
    _rec_name = "product_id"
    _order = "request_id desc, sequence, id"
    _check_company_auto = True

    request_id = fields.Many2one("dvz.manual.reservation.request", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related="request_id.company_id", store=True, index=True)
    partner_id = fields.Many2one(related="request_id.partner_id", store=True, string="Customer")
    project_id = fields.Many2one(related="request_id.project_id", store=True, string="Project")
    sale_order_id = fields.Many2one(related="request_id.sale_order_id", store=True, string="SO Number")
    date = fields.Datetime(related="request_id.date", store=True, string="Scheduled Date")
    state = fields.Selection(related="request_id.state", store=True)
    product_id = fields.Many2one(
        "product.product", required=True, check_company=True, ondelete="restrict",
        domain="[('is_storable', '=', True)]",
    )
    product_uom_id = fields.Many2one(related="product_id.uom_id", string="Unit", store=True)
    requested_qty = fields.Float(string="Requested Qty", default=1.0, required=True, digits="Product Unit", aggregator=False)
    move_ids = fields.One2many("stock.move", "dvz_manual_request_line_id", string="Stock Moves", copy=False)
    reserved_qty = fields.Float(string="Reserved Qty", compute="_compute_quantities", store=True, digits="Product Unit", aggregator=False)
    delivered_qty = fields.Float(string="Delivered Qty", compute="_compute_quantities", store=True, digits="Product Unit", aggregator=False)
    remaining_qty = fields.Float(string="To Reserve", compute="_compute_quantities", store=True, digits="Product Unit", aggregator=False)

    @api.depends(
        "requested_qty", "product_uom_id", "request_id.state", "move_ids.quantity",
        "move_ids.state", "move_ids.product_uom", "move_ids.location_id.usage",
        "move_ids.location_dest_id.usage",
    )
    def _compute_quantities(self):
        for line in self:
            reserved = delivered = 0.0
            for move in line.move_ids:
                quantity = move.product_uom._compute_quantity(move.quantity, line.product_uom_id, round=False)
                if move.location_id.usage == "internal" and move.location_dest_id.usage == "customer":
                    if move.state == "done":
                        delivered += quantity
                    elif move.state not in ("draft", "cancel"):
                        reserved += quantity
                elif move.state == "done" and move.location_id.usage == "customer" and move.location_dest_id.usage == "internal":
                    delivered -= quantity
            line.reserved_qty = max(reserved, 0.0)
            line.delivered_qty = max(delivered, 0.0)
            line.remaining_qty = (
                max(line.requested_qty - max(delivered, 0.0) - reserved, 0.0)
                if line.request_id.state != "cancel" else 0.0
            )

    @api.constrains("requested_qty", "product_id")
    def _validate_materials(self):
        for line in self:
            if not line.product_id.is_storable:
                raise ValidationError(_("Select a product with inventory tracking enabled."))
            if not math.isfinite(line.requested_qty) or float_compare(
                line.requested_qty, 0.0, precision_rounding=line.product_uom_id.rounding,
            ) <= 0:
                raise ValidationError(_("Requested quantity must be positive at the product unit precision."))

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            self._check_input_fields(vals)
            if not vals.get("request_id") and self.env.context.get("default_request_id"):
                vals["request_id"] = self.env.context["default_request_id"]
        requests = self.env["dvz.manual.reservation.request"].browse([
            vals["request_id"] for vals in vals_list if vals.get("request_id")
        ])
        requests._lock_requests()
        if any(request.state != "draft" for request in requests):
            raise UserError(_("Materials can only be added to a draft request."))
        protected_defaults = {"default_" + field for field in self._derived_fields()}
        clean_context = {key: value for key, value in self.env.context.items() if key not in protected_defaults}
        lines = super(ManualReservationRequestLine, self.with_context(clean_context)).create(vals_list)
        requests._touch_line_revision()
        return lines

    def write(self, vals):
        self._check_input_fields(vals)
        requests = self.request_id
        requests._lock_requests()
        if {"product_id", "requested_qty", "request_id", "sequence"} & vals.keys():
            if vals.get("request_id"):
                requests |= self.env["dvz.manual.reservation.request"].browse(vals["request_id"])
                requests._lock_requests()
            if any(request.state != "draft" for request in requests):
                raise UserError(_("Materials on a confirmed or cancelled request cannot be edited."))
        result = super().write(vals)
        requests._touch_line_revision()
        return result

    @api.model
    def _check_input_fields(self, vals):
        if self._derived_fields() & vals.keys():
            raise UserError(_("Reservation references and stock quantities are calculated automatically."))

    @api.model
    def _derived_fields(self):
        return {
            "company_id", "partner_id", "project_id", "sale_order_id", "date", "state",
            "product_uom_id", "reserved_qty", "delivered_qty", "remaining_qty", "move_ids",
        }

    def unlink(self):
        requests = self.request_id
        requests._lock_requests()
        if any(line.request_id.state != "draft" or line.move_ids for line in self):
            raise UserError(_("Only draft request materials without stock moves can be deleted."))
        result = super().unlink()
        requests._touch_line_revision()
        return result
