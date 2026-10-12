from odoo import fields, models, tools

from ._utils import column_or_null, rate_sql

SALE_STATES = [
    ('draft', 'Quotation'), ('sent', 'Quotation Sent'), ('sale', 'Sales Order'),
    ('done', 'Locked'), ('cancel', 'Cancelled'),
]
INVOICE_STATUS = [
    ('upselling', 'Upselling Opportunity'), ('invoiced', 'Fully Invoiced'),
    ('to invoice', 'To Invoice'), ('no', 'Nothing to Invoice'),
]


class DvzProjectSaleReport(models.Model):
    """One row per sale order x project (analytic account): the price agreed
    with the client for that project."""
    _name = 'dvz.project.sale.report'
    _description = 'Project-wise Sale Order Report'
    _auto = False
    _rec_name = 'sale_id'
    _order = 'date_order desc, id desc'

    sale_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Project / Analytic Account', readonly=True)
    date_order = fields.Datetime(string='Order Date', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    user_id = fields.Many2one('res.users', string='Salesperson', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Order Currency', readonly=True)
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', readonly=True)
    state = fields.Selection(SALE_STATES, string='Status', readonly=True)
    invoice_status = fields.Selection(INVOICE_STATUS, string='Invoice Status', readonly=True)
    line_count = fields.Integer(string='Order Lines', readonly=True)
    project_amount_untaxed = fields.Monetary(
        string='Project Amount (order currency)', currency_field='currency_id', readonly=True)
    project_amount_company = fields.Monetary(
        string='Project Amount', currency_field='company_currency_id', readonly=True,
        help='This project\'s share of the sale order, untaxed, in company currency.')
    so_amount_total = fields.Monetary(
        string='Full Order Total (Tax Incl.)', currency_field='currency_id', readonly=True)

    def init(self):
        cr = self.env.cr
        tools.drop_view_if_exists(cr, self._table)
        rate = rate_sql(cr, 'sale_order', 'so')
        invoice_status = column_or_null(cr, 'sale_order', 'so', 'invoice_status', 'varchar')
        cr.execute(f'''
            CREATE VIEW {self._table} AS (
                WITH allocations AS (
                    SELECT
                        sol.id AS line_id,
                        sol.order_id,
                        aa.id AS analytic_account_id,
                        (dist.value::numeric / 100.0) AS allocation_ratio,
                        sol.price_subtotal,
                        {rate} AS rate
                    FROM sale_order_line sol
                    JOIN sale_order so ON so.id = sol.order_id
                    CROSS JOIN LATERAL jsonb_each_text(
                        COALESCE(sol.analytic_distribution::jsonb, '{{}}'::jsonb)) dist
                    CROSS JOIN LATERAL regexp_split_to_table(dist.key, ',') AS account_key
                    JOIN account_analytic_account aa ON aa.id::text = trim(account_key)
                    WHERE sol.display_type IS NULL
                )
                SELECT
                    (a.order_id::bigint * 1000000000 + a.analytic_account_id::bigint) AS id,
                    a.order_id AS sale_id,
                    a.analytic_account_id,
                    so.date_order,
                    so.partner_id,
                    so.user_id,
                    so.company_id,
                    so.currency_id,
                    rc.currency_id AS company_currency_id,
                    so.state,
                    {invoice_status} AS invoice_status,
                    COUNT(DISTINCT a.line_id)::integer AS line_count,
                    SUM(a.price_subtotal * a.allocation_ratio) AS project_amount_untaxed,
                    SUM(a.price_subtotal * a.allocation_ratio / a.rate) AS project_amount_company,
                    so.amount_total AS so_amount_total
                FROM allocations a
                JOIN sale_order so ON so.id = a.order_id
                JOIN res_company rc ON rc.id = so.company_id
                GROUP BY a.order_id, a.analytic_account_id, so.id, so.date_order,
                         so.partner_id, so.user_id, so.company_id, so.currency_id,
                         rc.currency_id, so.state, so.amount_total
            )
        ''')

    def action_open_sale_order(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'sale.order',
                'res_id': self.sale_id.id, 'view_mode': 'form', 'target': 'current'}


class DvzProjectSaleLine(models.Model):
    """One row per sale order line x project, with the project's share."""
    _name = 'dvz.project.sale.line'
    _description = 'Project Sale Order Line'
    _auto = False
    _rec_name = 'sale_id'
    _order = 'date_order desc, id desc'

    sale_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    sale_line_id = fields.Many2one('sale.order.line', string='Order Line', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Project', readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    user_id = fields.Many2one('res.users', string='Salesperson', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Order Currency', readonly=True)
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', readonly=True)
    date_order = fields.Datetime(string='Order Date', readonly=True)
    state = fields.Selection(SALE_STATES, string='Status', readonly=True)
    product_qty = fields.Float(string='Ordered Qty', readonly=True)
    qty_delivered = fields.Float(string='Delivered Qty', readonly=True)
    qty_invoiced = fields.Float(string='Invoiced Qty', readonly=True)
    price_unit = fields.Float(string='Unit Price', readonly=True)
    allocation_percent = fields.Float(string='Analytic %', readonly=True)
    price_subtotal = fields.Monetary(currency_field='currency_id', string='Line Subtotal', readonly=True)
    project_amount = fields.Monetary(
        currency_field='currency_id', string='Project Amount (order currency)', readonly=True)
    project_amount_company = fields.Monetary(
        currency_field='company_currency_id', string='Project Amount', readonly=True)

    def init(self):
        cr = self.env.cr
        tools.drop_view_if_exists(cr, self._table)
        rate = rate_sql(cr, 'sale_order', 'so')
        qty = column_or_null(cr, 'sale_order_line', 'sol', 'product_uom_qty', 'numeric')
        delivered = column_or_null(cr, 'sale_order_line', 'sol', 'qty_delivered', 'numeric')
        invoiced = column_or_null(cr, 'sale_order_line', 'sol', 'qty_invoiced', 'numeric')
        cr.execute(f'''
            CREATE VIEW {self._table} AS
            SELECT (sol.id::bigint * 1000000000 + aa.id::bigint) AS id,
                   sol.order_id AS sale_id, sol.id AS sale_line_id,
                   aa.id AS analytic_account_id, sol.product_id,
                   so.partner_id, so.user_id, so.company_id, so.currency_id,
                   rc.currency_id AS company_currency_id, so.date_order, so.state,
                   {qty} AS product_qty, {delivered} AS qty_delivered,
                   {invoiced} AS qty_invoiced, sol.price_unit,
                   (dist.value::numeric) AS allocation_percent,
                   sol.price_subtotal,
                   sol.price_subtotal * (dist.value::numeric / 100.0) AS project_amount,
                   sol.price_subtotal * (dist.value::numeric / 100.0) / {rate} AS project_amount_company
            FROM sale_order_line sol
            JOIN sale_order so ON so.id = sol.order_id
            JOIN res_company rc ON rc.id = so.company_id
            CROSS JOIN LATERAL jsonb_each_text(
                COALESCE(sol.analytic_distribution::jsonb, '{{}}'::jsonb)) dist
            CROSS JOIN LATERAL regexp_split_to_table(dist.key, ',') AS account_key
            JOIN account_analytic_account aa ON aa.id::text = trim(account_key)
            WHERE sol.display_type IS NULL
        ''')

    def action_open_sale_order(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'sale.order',
                'res_id': self.sale_id.id, 'view_mode': 'form', 'target': 'current'}
