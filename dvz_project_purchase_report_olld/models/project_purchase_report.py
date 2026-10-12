from odoo import fields, models, tools

from ._utils import rate_sql


class DvzProjectPurchaseReport(models.Model):
    _name = 'dvz.project.purchase.report'
    _description = 'Project-wise Purchase Order Report'
    _auto = False
    _rec_name = 'purchase_id'
    _order = 'date_order desc, id desc'

    owner_user_id = fields.Many2one('res.users', string='Responsible User', readonly=True)
    purchase_id = fields.Many2one('purchase.order', string='PO Reference', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Project / Analytic Account', readonly=True)
    date_order = fields.Datetime(string='Order Date', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Vendor', readonly=True)
    user_id = fields.Many2one('res.users', string='Buyer', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='PO Currency', readonly=True)
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', readonly=True)
    state = fields.Selection([
        ('draft', 'RFQ'), ('sent', 'RFQ Sent'), ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'), ('done', 'Locked'), ('cancel', 'Cancelled'),
    ], string='Status', readonly=True)
    product_line_count = fields.Integer(string='Product Lines', readonly=True)
    project_amount_untaxed = fields.Monetary(
        string='Project Amount (PO currency)', currency_field='currency_id', readonly=True)
    project_amount_company = fields.Monetary(
        string='Project Amount', currency_field='company_currency_id', readonly=True,
        help='This project\'s share of the PO, untaxed, converted to company currency.')
    po_amount_total = fields.Monetary(
        string='Full PO Total (Tax Incl.)', currency_field='currency_id', readonly=True)

    def init(self):
        cr = self.env.cr
        tools.drop_view_if_exists(cr, self._table)
        rate = rate_sql(cr, 'purchase_order', 'po')
        cr.execute(f'''
            CREATE VIEW {self._table} AS (
                WITH allocations AS (
                    SELECT
                        pol.id AS line_id,
                        pol.order_id,
                        (trim(project_key))::integer AS analytic_account_id,
                        (distribution.percentage::numeric / 100.0) AS allocation_ratio,
                        pol.price_subtotal,
                        {rate} AS rate
                    FROM purchase_order_line pol
                    JOIN purchase_order po ON po.id = pol.order_id
                    CROSS JOIN LATERAL jsonb_each_text(
                        COALESCE(pol.analytic_distribution::jsonb, '{{}}'::jsonb)
                    ) AS distribution(account_keys, percentage)
                    CROSS JOIN LATERAL regexp_split_to_table(
                        distribution.account_keys, ','
                    ) AS project_key
                    WHERE pol.display_type IS NULL
                      AND trim(project_key) ~ '^[0-9]+$'
                )
                SELECT
                    (a.order_id::bigint * 1000000000 + a.analytic_account_id::bigint) AS id,
                    a.order_id AS purchase_id,
                    a.analytic_account_id,
                    po.date_order,
                    po.partner_id,
                    po.user_id,
                    COALESCE(po.user_id, po.create_uid) AS owner_user_id,
                    po.company_id,
                    po.currency_id,
                    rc.currency_id AS company_currency_id,
                    po.state,
                    COUNT(DISTINCT a.line_id)::integer AS product_line_count,
                    SUM(a.price_subtotal * a.allocation_ratio) AS project_amount_untaxed,
                    SUM(a.price_subtotal * a.allocation_ratio / a.rate) AS project_amount_company,
                    po.amount_total AS po_amount_total
                FROM allocations a
                JOIN purchase_order po ON po.id = a.order_id
                JOIN res_company rc ON rc.id = po.company_id
                JOIN account_analytic_account aa ON aa.id = a.analytic_account_id
                GROUP BY a.order_id, a.analytic_account_id, po.id,
                         po.date_order, po.partner_id, po.user_id, po.company_id,
                         po.currency_id, rc.currency_id, po.state, po.amount_total
            )
        ''')

    def action_open_purchase_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': self.purchase_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
