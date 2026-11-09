from odoo import _, api, fields, models


def _project_share_percent(analytic_id, distribution):
    if not analytic_id:
        return 0.0
    total = 0.0
    for key, percent in (distribution or {}).items():
        account_ids = [part.strip() for part in str(key).split(',')]
        if str(analytic_id) in account_ids:
            total += float(percent or 0.0)
    return total


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    dvz_honeywell_delivery_costing = fields.Boolean(
        string='Honeywell Delivery Costing',
        help=(
            'Enable this only for projects where costing must be recognized from '
            'actual completed deliveries. Partial deliveries are costed line by line.'
        ),
    )
    dvz_delivery_cost_line_ids = fields.One2many(
        'dvz.project.delivery.cost.line',
        'analytic_account_id',
        string='Delivery Costing Lines',
        readonly=True,
    )
    dvz_delivery_cost_total = fields.Monetary(
        string='Delivered Cost',
        currency_field='dvz_delivery_cost_currency_id',
        compute='_compute_dvz_delivery_cost_total',
    )
    dvz_delivery_cost_count = fields.Integer(
        string='Delivery Cost Lines',
        compute='_compute_dvz_delivery_cost_total',
    )
    dvz_delivery_cost_currency_id = fields.Many2one(
        'res.currency',
        string='Cost Currency',
        compute='_compute_dvz_delivery_cost_currency_id',
    )

    @api.depends('company_id')
    def _compute_dvz_delivery_cost_currency_id(self):
        for account in self:
            account.dvz_delivery_cost_currency_id = (
                account.company_id or self.env.company
            ).currency_id

    def _compute_dvz_delivery_cost_total(self):
        CostLine = self.env['dvz.project.delivery.cost.line']
        for account in self:
            if not account.id:
                account.dvz_delivery_cost_total = 0.0
                account.dvz_delivery_cost_count = 0
                continue
            lines = CostLine.search([('analytic_account_id', '=', account.id)])
            account.dvz_delivery_cost_total = sum(lines.mapped('amount'))
            account.dvz_delivery_cost_count = len(lines)

    def _dvz_delivery_move_qty(self, move):
        # Odoo 19 uses stock.move.quantity for the done quantity. Keep this
        # fallback to make the extension tolerant of minor stock customisations.
        if 'quantity' in move._fields:
            return move.quantity or 0.0
        if 'quantity_done' in move._fields:
            return move.quantity_done or 0.0
        return 0.0

    def _dvz_move_actual_cost(self, move, qty):
        """Return actual company-currency cost of this completed delivery move."""
        svls = self.env['stock.valuation.layer'].search([
            ('stock_move_id', '=', move.id),
        ])
        if svls:
            # Outgoing valuation is normally negative, therefore negate it so
            # delivered project cost is positive.
            return -sum(svls.mapped('value'))
        # Fallback for unusual/custom valuation setups.
        return (move.product_id.standard_price or 0.0) * qty

    def _dvz_sync_delivery_cost_moves(self, moves):
        self.ensure_one()
        if not self.dvz_honeywell_delivery_costing or not self.id:
            return

        CostLine = self.env['dvz.project.delivery.cost.line']
        company = self.company_id or self.env.company
        currency = company.currency_id

        for move in moves.filtered(lambda m: m.state == 'done' and m.sale_line_id):
            # Only actual customer deliveries. Internal transfers and receipts
            # must never create project delivery cost lines.
            if move.location_dest_id.usage != 'customer':
                continue

            percent = _project_share_percent(
                self.id, move.sale_line_id.analytic_distribution
            )
            if not percent:
                continue

            qty = self._dvz_delivery_move_qty(move)
            if qty <= 0:
                continue

            full_move_cost = self._dvz_move_actual_cost(move, qty)
            project_cost = full_move_cost * percent / 100.0
            project_qty = qty * percent / 100.0
            unit_cost = project_cost / project_qty if project_qty else 0.0

            vals = {
                'analytic_account_id': self.id,
                'stock_move_id': move.id,
                'picking_id': move.picking_id.id,
                'sale_order_id': move.sale_line_id.order_id.id,
                'sale_line_id': move.sale_line_id.id,
                'product_id': move.product_id.id,
                'product_uom_id': move.product_uom.id,
                'delivered_qty': qty,
                'analytic_percent': percent,
                'unit_cost': unit_cost,
                'amount': project_cost,
                'currency_id': currency.id,
                'company_id': company.id,
                'delivery_date': move.picking_id.date_done or move.date,
            }

            existing = CostLine.search([
                ('analytic_account_id', '=', self.id),
                ('stock_move_id', '=', move.id),
            ], limit=1)
            if existing:
                existing.write(vals)
            else:
                CostLine.create(vals)

    def _dvz_sync_all_delivery_costs(self):
        for account in self.filtered('dvz_honeywell_delivery_costing'):
            sale_lines = self.env['sale.order.line'].search([
                ('analytic_distribution', '!=', False),
            ]).filtered(
                lambda line: _project_share_percent(
                    account.id, line.analytic_distribution
                ) > 0.0
            )
            if not sale_lines:
                continue
            moves = self.env['stock.move'].search([
                ('sale_line_id', 'in', sale_lines.ids),
                ('state', '=', 'done'),
                ('location_dest_id.usage', '=', 'customer'),
            ])
            account._dvz_sync_delivery_cost_moves(moves)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('dvz_honeywell_delivery_costing'):
            self.filtered('dvz_honeywell_delivery_costing')._dvz_sync_all_delivery_costs()
        return res

    def action_dvz_delivery_cost_lines(self):
        self.ensure_one()
        if self.dvz_honeywell_delivery_costing:
            self._dvz_sync_all_delivery_costs()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delivered Costing - %s') % self.display_name,
            'res_model': 'dvz.project.delivery.cost.line',
            'view_mode': 'list,form',
            'domain': [('analytic_account_id', '=', self.id)],
            'context': {
                'create': False,
                'delete': False,
                'default_analytic_account_id': self.id,
            },
        }
