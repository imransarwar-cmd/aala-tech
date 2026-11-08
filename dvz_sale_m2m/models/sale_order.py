from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    aala_division_ids = fields.Many2many(
        comodel_name='division.master',
        relation='aala_so_division_m2m_rel',
        column1='sale_order_id',
        column2='division_id',
        string='Division',
        help='Select one or more divisions for this quotation / sales order.',
    )

    aala_system_ids = fields.Many2many(
        comodel_name='system.master',
        relation='aala_so_system_m2m_rel',
        column1='sale_order_id',
        column2='system_id',
        string='System',
        domain="[('division', 'in', aala_division_ids)]",
        help='Only systems belonging to the selected divisions are available.',
    )

    @api.onchange('aala_division_ids')
    def _onchange_aala_division_ids(self):
        """Keep only systems that belong to one of the selected divisions."""
        for order in self:
            if not order.aala_division_ids:
                order.aala_system_ids = [(5, 0, 0)]
                continue
            valid_systems = order.aala_system_ids.filtered(
                lambda system: system.division in order.aala_division_ids
            )
            if valid_systems != order.aala_system_ids:
                order.aala_system_ids = valid_systems

    @api.onchange('aala_system_ids')
    def _onchange_aala_system_ids(self):
        """If systems are set programmatically, include their divisions as well."""
        for order in self:
            system_divisions = order.aala_system_ids.mapped('division')
            if system_divisions:
                order.aala_division_ids |= system_divisions

    def init(self):
        """Backfill existing single System data without deleting or changing it.

        The original sale.order.system Many2one remains untouched for compatibility.
        This only copies its current value to the new M2M fields and copies the
        corresponding system.master.division to the new Division M2M field.
        """
        self.env.cr.execute("""
            INSERT INTO aala_so_system_m2m_rel (sale_order_id, system_id)
            SELECT so.id, so.system
              FROM sale_order so
             WHERE so.system IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
        self.env.cr.execute("""
            INSERT INTO aala_so_division_m2m_rel (sale_order_id, division_id)
            SELECT so.id, sm.division
              FROM sale_order so
              JOIN system_master sm ON sm.id = so.system
             WHERE so.system IS NOT NULL
               AND sm.division IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
