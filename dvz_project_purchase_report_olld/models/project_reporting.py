from odoo import fields, models, tools

from ._utils import rate_sql

MOVE_TYPES = [
    ('out_invoice', 'Customer Invoice'), ('out_refund', 'Customer Credit Note'),
    ('in_invoice', 'Vendor Bill'), ('in_refund', 'Vendor Credit Note'),
]


class ProjectPurchaseLine(models.Model):
    _name = 'dvz.project.purchase.line'
    _description = 'Project Purchase Product Line'
    _auto = False
    _order = 'date_order desc, id desc'
    _rec_name = 'purchase_id'

    purchase_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)
    purchase_line_id = fields.Many2one('purchase.order.line', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Project', readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Vendor', readonly=True)
    owner_user_id = fields.Many2one('res.users', string='Responsible User', readonly=True)
    user_id = fields.Many2one('res.users', string='Buyer', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='PO Currency', readonly=True)
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', readonly=True)
    date_order = fields.Datetime(string='Order Date', readonly=True)
    state = fields.Char(string='Status', readonly=True)
    product_qty = fields.Float(string='Ordered Qty', readonly=True)
    qty_received = fields.Float(string='Received Qty', readonly=True)
    qty_invoiced = fields.Float(string='Billed Qty', readonly=True)
    price_unit = fields.Float(string='Unit Price', readonly=True)
    allocation_percent = fields.Float(string='Analytic %', readonly=True)
    price_subtotal = fields.Monetary(currency_field='currency_id', string='Line Subtotal', readonly=True)
    project_amount = fields.Monetary(
        currency_field='currency_id', string='Project Amount (PO currency)', readonly=True)
    project_amount_company = fields.Monetary(
        currency_field='company_currency_id', string='Project Amount', readonly=True)

    def init(self):
        cr = self.env.cr
        tools.drop_view_if_exists(cr, self._table)
        rate = rate_sql(cr, 'purchase_order', 'po')
        cr.execute(f"""
            CREATE VIEW {self._table} AS
            SELECT (pol.id::bigint * 1000000000 + aa.id::bigint) AS id,
                   pol.order_id AS purchase_id, pol.id AS purchase_line_id,
                   aa.id AS analytic_account_id, pol.product_id,
                   po.partner_id, po.user_id,
                   COALESCE(po.user_id, po.create_uid) AS owner_user_id,
                   po.company_id, po.currency_id, rc.currency_id AS company_currency_id,
                   po.date_order, po.state,
                   pol.product_qty, pol.qty_received, pol.qty_invoiced,
                   pol.price_unit, (dist.value::numeric) AS allocation_percent,
                   pol.price_subtotal,
                   pol.price_subtotal * (dist.value::numeric / 100.0) AS project_amount,
                   pol.price_subtotal * (dist.value::numeric / 100.0) / {rate} AS project_amount_company
            FROM purchase_order_line pol
            JOIN purchase_order po ON po.id = pol.order_id
            JOIN res_company rc ON rc.id = po.company_id
            CROSS JOIN LATERAL jsonb_each_text(COALESCE(pol.analytic_distribution::jsonb, '{{}}'::jsonb)) dist
            CROSS JOIN LATERAL regexp_split_to_table(dist.key, ',') AS account_key
            JOIN account_analytic_account aa ON aa.id::text = trim(account_key)
            WHERE pol.display_type IS NULL
        """)

    def action_open_purchase_order(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'purchase.order',
                'res_id': self.purchase_id.id, 'view_mode': 'form'}


class ProjectInvoiceLine(models.Model):
    _name = 'dvz.project.invoice.line'
    _description = 'Project Invoice and Vendor Bill Line'
    _auto = False
    _order = 'invoice_date desc, id desc'
    _rec_name = 'move_id'

    move_id = fields.Many2one('account.move', string='Invoice / Bill', readonly=True)
    move_line_id = fields.Many2one('account.move.line', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Project', readonly=True)
    move_type = fields.Selection(MOVE_TYPES, string='Type', readonly=True)
    partner_id = fields.Many2one('res.partner', readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    owner_user_id = fields.Many2one('res.users', string='Responsible User', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Document Currency', readonly=True)
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', readonly=True)
    invoice_date = fields.Date(readonly=True)
    invoice_date_due = fields.Date(readonly=True)
    payment_state = fields.Char(readonly=True)
    state = fields.Char(string='Status', readonly=True)
    quantity = fields.Float(readonly=True)
    price_unit = fields.Float(string='Unit Price', readonly=True)
    allocation_percent = fields.Float(string='Analytic %', readonly=True)
    line_subtotal = fields.Monetary(currency_field='currency_id', readonly=True)
    project_amount = fields.Monetary(
        currency_field='currency_id', string='Project Amount (document currency)', readonly=True)
    project_amount_company = fields.Monetary(
        currency_field='company_currency_id', string='Project Amount', readonly=True)

    def init(self):
        cr = self.env.cr
        # Drop dependent aggregate view first during module upgrades.
        tools.drop_view_if_exists(cr, 'dvz_project_invoice_report')
        tools.drop_view_if_exists(cr, self._table)
        # project_amount_company uses the line's own company-currency balance
        # (booked at the invoice's rate): cost lines are positive, revenue lines
        # are sign-flipped to positive, credit notes come out negative.
        cr.execute(f"""
            CREATE VIEW {self._table} AS
            SELECT (aml.id::bigint * 1000000000 + aa.id::bigint) AS id,
                   am.id AS move_id, aml.id AS move_line_id, aa.id AS analytic_account_id,
                   am.move_type, am.partner_id, aml.product_id,
                   COALESCE(am.invoice_user_id, am.create_uid) AS owner_user_id,
                   am.company_id, am.currency_id, rc.currency_id AS company_currency_id,
                   am.invoice_date, am.invoice_date_due,
                   am.payment_state, am.state, aml.quantity, aml.price_unit,
                   dist.value::numeric AS allocation_percent,
                   aml.price_subtotal AS line_subtotal,
                   (CASE WHEN am.move_type IN ('in_refund', 'out_refund') THEN -1 ELSE 1 END)
                   * aml.price_subtotal * (dist.value::numeric / 100.0) AS project_amount,
                   (CASE WHEN am.move_type IN ('in_invoice', 'in_refund') THEN aml.balance
                         ELSE -aml.balance END)
                   * (dist.value::numeric / 100.0) AS project_amount_company
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN res_company rc ON rc.id = am.company_id
            CROSS JOIN LATERAL jsonb_each_text(COALESCE(aml.analytic_distribution::jsonb, '{{}}'::jsonb)) dist
            CROSS JOIN LATERAL regexp_split_to_table(dist.key, ',') AS account_key
            JOIN account_analytic_account aa ON aa.id::text = trim(account_key)
            WHERE am.move_type IN ('in_invoice', 'in_refund', 'out_invoice', 'out_refund')
              AND aml.display_type = 'product'
        """)

    def action_open_invoice(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move',
                'res_id': self.move_id.id, 'view_mode': 'form'}


class ProjectInvoiceReport(models.Model):
    _name = 'dvz.project.invoice.report'
    _description = 'Project Invoice and Vendor Bill Report'
    _auto = False
    _order = 'invoice_date desc, id desc'
    _rec_name = 'move_id'

    move_id = fields.Many2one('account.move', string='Invoice / Bill', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Project', readonly=True)
    move_type = fields.Selection(MOVE_TYPES, string='Type', readonly=True)
    partner_id = fields.Many2one('res.partner', readonly=True)
    owner_user_id = fields.Many2one('res.users', string='Responsible User', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Document Currency', readonly=True)
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', readonly=True)
    invoice_date = fields.Date(readonly=True)
    invoice_date_due = fields.Date(readonly=True)
    payment_state = fields.Char(readonly=True)
    state = fields.Char(string='Status', readonly=True)
    line_count = fields.Integer(string='Lines', readonly=True)
    project_amount = fields.Monetary(
        currency_field='currency_id', string='Project Amount (document currency)', readonly=True)
    project_amount_company = fields.Monetary(
        currency_field='company_currency_id', string='Project Amount', readonly=True)
    full_invoice_total = fields.Monetary(currency_field='currency_id', readonly=True)

    def init(self):
        cr = self.env.cr
        tools.drop_view_if_exists(cr, self._table)
        cr.execute(f"""
            CREATE VIEW {self._table} AS
            SELECT (r.move_id::bigint * 1000000000 + r.analytic_account_id::bigint) AS id,
                   r.move_id, r.analytic_account_id, r.move_type, r.partner_id,
                   r.owner_user_id, r.company_id, r.currency_id, r.company_currency_id,
                   r.invoice_date, r.invoice_date_due, r.payment_state, r.state,
                   COUNT(DISTINCT r.move_line_id)::integer AS line_count,
                   SUM(r.project_amount) AS project_amount,
                   SUM(r.project_amount_company) AS project_amount_company,
                   am.amount_total AS full_invoice_total
            FROM dvz_project_invoice_line r
            JOIN account_move am ON am.id = r.move_id
            GROUP BY r.move_id, r.analytic_account_id, r.move_type, r.partner_id,
                     r.owner_user_id, r.company_id, r.currency_id, r.company_currency_id,
                     r.invoice_date, r.invoice_date_due, r.payment_state, r.state,
                     am.amount_total
        """)

    def action_open_invoice(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move',
                'res_id': self.move_id.id, 'view_mode': 'form'}
