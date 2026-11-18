from odoo import Command, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_dvz_supply_report(self):
        self.check_access('read')
        action = self.env['ir.actions.actions']._for_xml_id(
            'dvz_sale_supply_report.action_dvz_sale_supply_report')
        action['domain'] = [
            ('order_id', 'in', self.ids), ('display_type', '=', False),
            ('is_downpayment', '=', False), ('product_id', '!=', False),
        ]
        action['context'] = dict(self.env.context, search_default_confirmed=0)
        return action

    def action_dvz_supply_export(self):
        self.check_access('read')
        action = self.env['ir.actions.actions']._for_xml_id(
            'dvz_sale_supply_report.action_dvz_sale_supply_export')
        context = dict(self.env.context)
        for name in ('default_scope', 'default_sale_line_ids', 'default_product_ids'):
            context.pop(name, None)
        context.update(
            default_order_ids=[Command.set(self.ids)],
            active_model='sale.order', active_ids=self.ids,
            active_id=self.id if len(self) == 1 else False,
        )
        action['context'] = context
        return action
