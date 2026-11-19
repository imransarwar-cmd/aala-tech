from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # Keep the prior manual addon's technical names and values during upgrades.
    dvz_manual_project_id = fields.Many2one(
        "project.project", string="Reservation Project", copy=False, check_company=True,
    )
    dvz_manual_so_id = fields.Many2one(
        "sale.order", string="SO Reference", copy=False, check_company=True,
        help="Informational quotation reference; this manual transfer is separate from an SO delivery.",
    )
