from odoo import api, fields, models
from .view_utils import protect_view


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    dvz_can_manage_lock = fields.Boolean(
        compute="_compute_dvz_lock_permissions", compute_sudo=False,
    )
    dvz_lock_readonly = fields.Boolean(
        compute="_compute_dvz_lock_permissions", compute_sudo=False,
    )

    @api.depends("order_id", "order_id.locked")
    @api.depends_context("uid")
    def _compute_dvz_lock_permissions(self):
        permitted = self.env["sale.order"]._dvz_is_locked_editor()
        for line in self:
            line.dvz_can_manage_lock = permitted
            line.dvz_lock_readonly = bool(line.order_id.locked)

    @api.model_create_multi
    def create(self, vals_list):
        default_order = self.default_get(["order_id"]).get("order_id")
        order_ids = set()
        for vals in vals_list:
            self.env["sale.order"]._dvz_reject_control_values(vals)
            order_id = vals.get("order_id", default_order)
            if order_id:
                order_ids.add(order_id)
        self.env["sale.order"].browse(sorted(order_ids))._dvz_assert_editable()
        return super().create(vals_list)

    def write(self, vals):
        self.env["sale.order"]._dvz_reject_control_values(vals)
        if vals:
            orders = self.order_id
            if vals.get("order_id"):
                orders |= self.env["sale.order"].browse(vals["order_id"])
            orders._dvz_assert_editable()
        return super().write(vals)

    def unlink(self):
        self.order_id._dvz_assert_editable()
        return super().unlink()

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type in {"form", "list", "tree"}:
            def relation(model, name):
                field = self.env[model]._fields.get(name)
                return getattr(field, "comodel_name", None)
            protect_view(arch, self._name, relation)
        return arch, view
