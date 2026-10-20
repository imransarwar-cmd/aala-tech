from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dvz_linked_invoice_ids = fields.Many2many(
        'account.move', 'dvz_sale_order_invoice_ref_rel', 'order_id', 'move_id',
        string='DVZ Referenced Invoices', copy=False,
        help='Reference only; does not modify accounting or sale order lines.',
        groups='sales_team.group_sale_salesman',
    )
    dvz_linked_invoice_count = fields.Integer(
        string='Linked Invoices', compute='_compute_dvz_linked_invoice_count',
    )

    @api.depends('dvz_linked_invoice_ids')
    def _compute_dvz_linked_invoice_count(self):
        for order in self:
            order.dvz_linked_invoice_count = len(order.dvz_linked_invoice_ids)

    @api.constrains('dvz_linked_invoice_ids', 'company_id', 'partner_id')
    def _check_dvz_linked_invoices(self):
        for order in self:
            for move in order.dvz_linked_invoice_ids:
                if move.move_type != 'out_invoice':
                    raise ValidationError(_('Only customer invoices can be referenced.'))
                if move.company_id != order.company_id:
                    raise ValidationError(_('Invoice and Sales Order must have the same company.'))
                if move.commercial_partner_id != order.partner_id.commercial_partner_id:
                    raise ValidationError(_('Invoice and Sales Order must have the same commercial customer.'))
                if move.currency_id != order.currency_id:
                    raise ValidationError(_('Invoice and Sales Order currencies must match.'))

    def action_view_dvz_linked_invoices(self):
        self.ensure_one()
        invoices = self.dvz_linked_invoice_ids.exists()
        action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
        action['domain'] = [('id', 'in', invoices.ids)]
        action['context'] = dict(self.env.context, default_move_type='out_invoice', create=False)
        action['name'] = _('Linked Invoices')
        if len(invoices) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = invoices.id
        else:
            action['views'] = [(False, 'list'), (False, 'form')]
            action.pop('res_id', None)
        return action

    def init(self):
        """Install/upgrade UI using Python; no XML data file required.

        Only touches this addon's own ir.ui.view records, never SO/invoice data.
        """
        View = self.env['ir.ui.view'].sudo()
        old = self.env.ref('dvz_so_invoice_link.dvz_sale_order_invoice_smart_button', raise_if_not_found=False)
        if old and old._name == 'ir.ui.view':
            old.unlink()  # Remove previous broken smart-button override.
        arch = '''<data>
          <xpath expr="//div[@name='button_box']" position="inside">
            <button name="action_view_dvz_linked_invoices" type="object"
                    class="oe_stat_button" icon="fa-link"
                    groups="sales_team.group_sale_salesman">
              <field name="dvz_linked_invoice_count" widget="statinfo" string="Linked Invoices"/>
            </button>
          </xpath>
        </data>'''
        vals = {
            'name': 'sale.order.form.dvz.linked.invoices.button',
            'type': 'form', 'model': 'sale.order',
            'inherit_id': self.env.ref('sale.view_order_form').id,
            'arch_db': arch,
        }
        existing = View.search([('name', '=', vals['name']), ('model', '=', 'sale.order')])
        if existing:
            existing[:1].write(vals)
            (existing - existing[:1]).unlink()
        else:
            View.create(vals)
