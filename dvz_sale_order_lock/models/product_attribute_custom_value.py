from odoo import api, models


class ProductAttributeCustomValue(models.Model):
    _inherit = "product.attribute.custom.value"

    @api.model_create_multi
    def create(self, vals_list):
        default_line = self.default_get(["sale_order_line_id"]).get("sale_order_line_id")
        line_ids = {
            vals.get("sale_order_line_id", default_line)
            for vals in vals_list
            if vals.get("sale_order_line_id", default_line)
        }
        self.env["sale.order.line"].browse(sorted(line_ids)).order_id._dvz_assert_editable()
        return super().create(vals_list)

    def write(self, vals):
        if vals:
            lines = self.sale_order_line_id
            if vals.get("sale_order_line_id"):
                lines |= self.env["sale.order.line"].browse(vals["sale_order_line_id"])
            lines.order_id._dvz_assert_editable()
        return super().write(vals)

    def unlink(self):
        self.sale_order_line_id.order_id._dvz_assert_editable()
        return super().unlink()
