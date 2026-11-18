from odoo import _, api, fields, models

from .delivery_costing_policy import get_delivery_costing_policy


def _distribution_has_account(distribution, analytic_id):
    """True when an Odoo analytic_distribution JSON key contains analytic_id.

    Keys can be a single id ("12") or a comma-separated combination ("12,34").
    """
    if not analytic_id or not distribution:
        return False
    target = str(analytic_id)
    for key in distribution:
        if target in [part.strip() for part in str(key).split(',')]:
            return True
    return False


def _distribution_account_ids(distribution):
    ids = set()
    for key in (distribution or {}):
        for part in str(key).split(','):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
    return ids


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    dvz_project_delivery_costing = fields.Boolean(
        string='Project Delivery Costing',
        compute='_compute_dvz_project_delivery_costing',
        help=(
            'Enabled by the Project Delivery Costing configuration. Delivered '
            'Cost is calculated from completed customer delivery moves of Sales '
            'Order lines assigned to this analytic account.'
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

    def _compute_dvz_project_delivery_costing(self):
        scope, account_ids = get_delivery_costing_policy(self.env)
        for account in self:
            account_id = account._origin.id or account.id
            account.dvz_project_delivery_costing = scope == 'all' or (
                scope == 'selected' and account_id in account_ids
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

    def _dvz_sale_lines(self):
        """Sales Order lines that belong directly to this analytic account.

        Primary rule: sale.order.line.analytic_distribution contains this account.
        Optional fallback: if the database already has a direct analytic-account
        field on sale.order, use it as well. We deliberately do not inspect
        project.project, task_id, project_id, or generated project links.
        """
        self.ensure_one()
        SaleLine = self.env['sale.order.line']
        lines = SaleLine.search([('analytic_distribution', 'in', [self.id])])

        SaleOrder = self.env['sale.order']
        for fname in ('analytic_account_id', 'account_analytic_id', 'analytic_id'):
            field = SaleOrder._fields.get(fname)
            if field and getattr(field, 'comodel_name', None) == 'account.analytic.account':
                orders = SaleOrder.search([(fname, '=', self.id)])
                if orders:
                    lines |= orders.order_line
        return lines.exists()

    def _dvz_delivery_move_qty(self, move):
        if 'quantity' in move._fields:
            return move.quantity or 0.0
        if 'quantity_done' in move._fields:
            return move.quantity_done or 0.0
        return 0.0

    def _dvz_qty_in_sale_uom(self, move, qty):
        sale_line = move.sale_line_id
        sale_uom = sale_line.product_uom_id
        move_uom = move.product_uom
        if sale_uom and move_uom and sale_uom != move_uom:
            return move_uom._compute_quantity(qty, sale_uom)
        return qty

    def _dvz_move_sale_value(self, move, move_qty):
        """SO price_unit x quantity actually delivered, in company currency."""
        sale_line = move.sale_line_id
        company = self.company_id or self.env.company
        company_currency = company.currency_id
        order_currency = sale_line.order_id.currency_id or company_currency

        sale_qty = self._dvz_qty_in_sale_uom(move, move_qty)
        unit_price = sale_line.price_unit or 0.0
        if order_currency != company_currency:
            conversion_date = (
                move.picking_id.date_done.date()
                if move.picking_id.date_done
                else fields.Date.context_today(self)
            )
            unit_price = order_currency._convert(
                unit_price,
                company_currency,
                company,
                conversion_date,
            )
        return sale_qty, unit_price, unit_price * sale_qty

    def _dvz_sync_delivery_cost_moves(self, moves):
        self.ensure_one()
        if not self.dvz_project_delivery_costing or not self.id:
            return

        valid_sale_lines = self._dvz_sale_lines()
        if not valid_sale_lines:
            return
        valid_line_ids = set(valid_sale_lines.ids)

        CostLine = self.env['dvz.project.delivery.cost.line'].sudo()
        company = self.company_id or self.env.company
        currency = company.currency_id

        for move in moves.filtered(
            lambda m: m.state == 'done'
            and m.sale_line_id
            and m.sale_line_id.id in valid_line_ids
            and m.location_dest_id.usage == 'customer'
        ):
            move_qty = self._dvz_delivery_move_qty(move)
            if move_qty <= 0:
                continue

            delivered_qty, unit_price, delivered_value = self._dvz_move_sale_value(move, move_qty)
            sale_line = move.sale_line_id

            vals = {
                'analytic_account_id': self.id,
                'stock_move_id': move.id,
                'picking_id': move.picking_id.id,
                'sale_order_id': sale_line.order_id.id,
                'sale_line_id': sale_line.id,
                'product_id': move.product_id.id,
                'product_uom_id': sale_line.product_uom_id.id,
                'delivered_qty': delivered_qty,
                'analytic_percent': 100.0,
                'unit_cost': unit_price,
                'amount': delivered_value,
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
        StockMove = self.env['stock.move']
        for account in self.filtered('dvz_project_delivery_costing'):
            sale_lines = account._dvz_sale_lines()
            if not sale_lines:
                continue
            moves = StockMove.search([
                ('state', '=', 'done'),
                ('sale_line_id', 'in', sale_lines.ids),
                ('location_dest_id.usage', '=', 'customer'),
            ])
            account._dvz_sync_delivery_cost_moves(moves)

    def action_dvz_delivery_cost_lines(self):
        self.ensure_one()
        if self.dvz_project_delivery_costing:
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
