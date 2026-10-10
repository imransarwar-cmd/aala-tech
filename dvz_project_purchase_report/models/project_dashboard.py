from odoo import fields, models, tools
from odoo.tools.safe_eval import safe_eval

from ._utils import column_or_null, rate_sql


class ProjectDashboard(models.Model):
    """One row per project (analytic account) x company, with everything in
    COMPANY currency and untaxed:

      Agreed price     confirmed sale orders (what the client agreed to pay)
      Budget           estimated cost typed on the analytic account
      Committed        confirmed purchase orders
      Billed           posted vendor bills (credit notes subtract)
      Invoiced         posted customer invoices (credit notes subtract)

      Expected profit  = agreed - committed        (what you stand to make)
      Actual profit    = invoiced - billed         (what is booked so far)
      Planned profit   = agreed - budget           (what you planned to make)
    """
    _name = 'dvz.project.dashboard'
    _description = 'Project Financial Dashboard'
    _auto = False
    _rec_name = 'analytic_account_id'
    _order = 'agreed_amount desc, id desc'

    analytic_account_id = fields.Many2one('account.analytic.account', string='Project', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    plan_id = fields.Many2one('account.analytic.plan', string='Plan', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    agreed_amount = fields.Monetary(string='Agreed Price', currency_field='currency_id', readonly=True,
                                    help='Confirmed sale orders allocated to this project.')
    budget = fields.Monetary(string='Estimated Budget', currency_field='currency_id', readonly=True,
                             help='Set on the analytic account (Project Budget).')
    po_commitment = fields.Monetary(string='Committed Cost (POs)', currency_field='currency_id', readonly=True,
                                    help='Confirmed purchase orders allocated to this project.')
    still_to_bill = fields.Monetary(string='Still to Bill', currency_field='currency_id', readonly=True,
                                    help='Part of the confirmed POs not yet billed by the vendors.')
    billed_cost = fields.Monetary(string='Billed Cost (Vendor Bills)', currency_field='currency_id', readonly=True,
                                  help='Posted vendor bills allocated to this project.')
    draft_bills = fields.Monetary(string='Draft Bills', currency_field='currency_id', readonly=True,
                                  help='Vendor bills not yet posted - not counted in Billed Cost.')
    revenue = fields.Monetary(string='Invoiced Revenue', currency_field='currency_id', readonly=True,
                              help='Posted customer invoices allocated to this project.')
    to_invoice = fields.Monetary(string='Still to Invoice', currency_field='currency_id', readonly=True,
                                 help='Agreed price minus what has been invoiced.')
    invoiced_percent = fields.Float(string='Invoiced %', digits=(16, 1), readonly=True)

    expected_profit = fields.Monetary(string='Expected Profit', currency_field='currency_id', readonly=True,
                                      help='Agreed price minus committed cost.')
    expected_margin = fields.Float(string='Expected Margin %', digits=(16, 1), readonly=True)
    profit = fields.Monetary(string='Actual Profit to Date', currency_field='currency_id', readonly=True,
                             help='Invoiced revenue minus billed cost.')
    margin_percent = fields.Float(string='Actual Margin %', digits=(16, 1), readonly=True)
    planned_profit = fields.Monetary(string='Planned Profit', currency_field='currency_id', readonly=True,
                                     help='Agreed price minus estimated budget (only if a budget is set).')
    planned_margin = fields.Float(string='Planned Margin %', digits=(16, 1), readonly=True)
    budget_remaining = fields.Monetary(string='Budget Remaining', currency_field='currency_id', readonly=True,
                                       help='Budget minus committed cost (only if a budget is set).')
    budget_used_percent = fields.Float(string='Budget Used %', digits=(16, 1), readonly=True,
                                       help='Committed cost as a % of the budget.')

    so_count = fields.Integer(string='Sale Orders', readonly=True)
    po_count = fields.Integer(string='Purchase Orders', readonly=True)
    bill_count = fields.Integer(string='Vendor Bills', readonly=True)
    invoice_count = fields.Integer(string='Customer Invoices', readonly=True)

    def init(self):
        cr = self.env.cr
        tools.drop_view_if_exists(cr, self._table)
        # The budget column is normally created by the ORM before this runs
        # (analytic_account is imported first); this is a harmless safety net.
        cr.execute("ALTER TABLE account_analytic_account ADD COLUMN IF NOT EXISTS dvz_budget numeric")
        so_rate = rate_sql(cr, 'sale_order', 'so')
        po_rate = rate_sql(cr, 'purchase_order', 'po')
        partner = column_or_null(cr, 'account_analytic_account', 'aa', 'partner_id')
        plan = column_or_null(cr, 'account_analytic_account', 'aa', 'plan_id')
        cr.execute(f'''
            CREATE VIEW {self._table} AS
            WITH sales AS (
                SELECT aa.id AS aid, so.company_id AS cid,
                       SUM(sol.price_subtotal * (dist.value::numeric / 100.0) / {so_rate}) AS amount,
                       COUNT(DISTINCT so.id)::integer AS doc_count
                FROM sale_order_line sol
                JOIN sale_order so ON so.id = sol.order_id
                CROSS JOIN LATERAL jsonb_each_text(COALESCE(sol.analytic_distribution::jsonb, '{{}}'::jsonb)) dist
                CROSS JOIN LATERAL regexp_split_to_table(dist.key, ',') AS account_key
                JOIN account_analytic_account aa ON aa.id::text = trim(account_key)
                WHERE sol.display_type IS NULL AND so.state IN ('sale', 'done')
                GROUP BY aa.id, so.company_id
            ),
            purchases AS (
                SELECT aa.id AS aid, po.company_id AS cid,
                       SUM(pol.price_subtotal * (dist.value::numeric / 100.0) / {po_rate}) AS amount,
                       SUM(pol.price_subtotal * (dist.value::numeric / 100.0) / {po_rate}
                           * GREATEST(0, 1 - COALESCE(pol.qty_invoiced, 0) / NULLIF(pol.product_qty, 0))) AS to_bill,
                       COUNT(DISTINCT po.id)::integer AS doc_count
                FROM purchase_order_line pol
                JOIN purchase_order po ON po.id = pol.order_id
                CROSS JOIN LATERAL jsonb_each_text(COALESCE(pol.analytic_distribution::jsonb, '{{}}'::jsonb)) dist
                CROSS JOIN LATERAL regexp_split_to_table(dist.key, ',') AS account_key
                JOIN account_analytic_account aa ON aa.id::text = trim(account_key)
                WHERE pol.display_type IS NULL AND po.state IN ('purchase', 'done')
                GROUP BY aa.id, po.company_id
            ),
            bills AS (
                SELECT aa.id AS aid, am.company_id AS cid,
                       SUM(CASE WHEN am.state = 'posted'
                                THEN aml.balance * (dist.value::numeric / 100.0) ELSE 0 END) AS posted_amount,
                       SUM(CASE WHEN am.state = 'draft'
                                THEN aml.balance * (dist.value::numeric / 100.0) ELSE 0 END) AS draft_amount,
                       COUNT(DISTINCT CASE WHEN am.state = 'posted' THEN am.id END)::integer AS doc_count
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                CROSS JOIN LATERAL jsonb_each_text(COALESCE(aml.analytic_distribution::jsonb, '{{}}'::jsonb)) dist
                CROSS JOIN LATERAL regexp_split_to_table(dist.key, ',') AS account_key
                JOIN account_analytic_account aa ON aa.id::text = trim(account_key)
                WHERE am.move_type IN ('in_invoice', 'in_refund')
                  AND aml.display_type = 'product'
                  AND am.state IN ('posted', 'draft')
                GROUP BY aa.id, am.company_id
            ),
            invoices AS (
                SELECT aa.id AS aid, am.company_id AS cid,
                       SUM(-aml.balance * (dist.value::numeric / 100.0)) AS posted_amount,
                       COUNT(DISTINCT am.id)::integer AS doc_count
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                CROSS JOIN LATERAL jsonb_each_text(COALESCE(aml.analytic_distribution::jsonb, '{{}}'::jsonb)) dist
                CROSS JOIN LATERAL regexp_split_to_table(dist.key, ',') AS account_key
                JOIN account_analytic_account aa ON aa.id::text = trim(account_key)
                WHERE am.move_type IN ('out_invoice', 'out_refund')
                  AND aml.display_type = 'product'
                  AND am.state = 'posted'
                GROUP BY aa.id, am.company_id
            ),
            keys AS (
                SELECT aid, cid FROM sales
                UNION SELECT aid, cid FROM purchases
                UNION SELECT aid, cid FROM bills
                UNION SELECT aid, cid FROM invoices
            ),
            base AS (
                SELECT k.aid, k.cid,
                       {partner} AS partner_id, {plan} AS plan_id,
                       COALESCE(aa.dvz_budget, 0) AS budget,
                       COALESCE(s.amount, 0) AS agreed,
                       COALESCE(p.amount, 0) AS committed,
                       COALESCE(p.to_bill, 0) AS to_bill,
                       COALESCE(b.posted_amount, 0) AS billed,
                       COALESCE(b.draft_amount, 0) AS draft_bills,
                       COALESCE(i.posted_amount, 0) AS revenue,
                       COALESCE(s.doc_count, 0) AS so_count,
                       COALESCE(p.doc_count, 0) AS po_count,
                       COALESCE(b.doc_count, 0) AS bill_count,
                       COALESCE(i.doc_count, 0) AS invoice_count
                FROM keys k
                JOIN account_analytic_account aa ON aa.id = k.aid
                LEFT JOIN sales s ON s.aid = k.aid AND s.cid = k.cid
                LEFT JOIN purchases p ON p.aid = k.aid AND p.cid = k.cid
                LEFT JOIN bills b ON b.aid = k.aid AND b.cid = k.cid
                LEFT JOIN invoices i ON i.aid = k.aid AND i.cid = k.cid
            )
            SELECT (b.aid::bigint * 1000000 + b.cid::bigint) AS id,
                   b.aid AS analytic_account_id,
                   b.cid AS company_id,
                   rc.currency_id AS currency_id,
                   b.partner_id,
                   b.plan_id,
                   b.agreed AS agreed_amount,
                   b.budget,
                   b.committed AS po_commitment,
                   b.to_bill AS still_to_bill,
                   b.billed AS billed_cost,
                   b.draft_bills,
                   b.revenue,
                   (b.agreed - b.revenue) AS to_invoice,
                   CASE WHEN b.agreed <> 0 THEN b.revenue / b.agreed * 100 ELSE 0 END AS invoiced_percent,
                   (b.agreed - b.committed) AS expected_profit,
                   CASE WHEN b.agreed <> 0 THEN (b.agreed - b.committed) / b.agreed * 100 ELSE 0 END AS expected_margin,
                   (b.revenue - b.billed) AS profit,
                   CASE WHEN b.revenue <> 0 THEN (b.revenue - b.billed) / b.revenue * 100 ELSE 0 END AS margin_percent,
                   CASE WHEN b.budget > 0 THEN b.agreed - b.budget ELSE 0 END AS planned_profit,
                   CASE WHEN b.budget > 0 AND b.agreed <> 0
                        THEN (b.agreed - b.budget) / b.agreed * 100 ELSE 0 END AS planned_margin,
                   CASE WHEN b.budget > 0 THEN b.budget - b.committed ELSE 0 END AS budget_remaining,
                   CASE WHEN b.budget > 0 THEN b.committed / b.budget * 100 ELSE 0 END AS budget_used_percent,
                   b.so_count, b.po_count, b.bill_count, b.invoice_count
            FROM base b
            JOIN res_company rc ON rc.id = b.cid
        ''')

    # ------------------------------------------------------------------
    # Drill-down buttons
    # ------------------------------------------------------------------
    def _open_report(self, xml_id, extra_domain=None, title=None):
        self.ensure_one()
        action = self.env.ref(xml_id).read()[0]
        # KEEP the action's own domain (e.g. vendor bills vs customer invoices
        # share one model) and add the project / company filter on top.
        base_domain = safe_eval(action.get('domain') or '[]')
        action['domain'] = base_domain + [
            ('analytic_account_id', '=', self.analytic_account_id.id),
            ('company_id', '=', self.company_id.id),
        ] + (extra_domain or [])
        action['context'] = {}
        action['name'] = '%s - %s' % (title or action['name'], self.analytic_account_id.display_name)
        return action

    def action_sale_orders(self):
        return self._open_report('dvz_project_purchase_report.action_dvz_project_sale_report',
                                 [('state', 'in', ('sale', 'done'))], 'Sale Orders')

    def action_purchase_orders(self):
        return self._open_report('dvz_project_purchase_report.action_dvz_project_purchase_report',
                                 [('state', 'in', ('purchase', 'done'))], 'Purchase Orders')

    def action_bills(self):
        return self._open_report('dvz_project_purchase_report.action_vendor_bills',
                                 [('state', '=', 'posted')], 'Vendor Bills')

    def action_invoices(self):
        return self._open_report('dvz_project_purchase_report.action_customer_invoices',
                                 [('state', '=', 'posted')], 'Customer Invoices')

    def action_open_analytic_account(self):
        """Open the analytic account (to type or change the Estimated Budget)."""
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.analytic.account',
                'res_id': self.analytic_account_id.id, 'view_mode': 'form', 'target': 'current'}
