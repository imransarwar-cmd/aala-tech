from odoo import fields, models


class Project(models.Model):
    _inherit = 'project.project'

    dvz_material_reservation_count = fields.Integer(compute='_compute_dvz_material_count', compute_sudo=False, groups="stock.group_stock_user,sales_team.group_sale_salesman")

    def _compute_dvz_material_count(self):
        for record in self:
            record.dvz_material_reservation_count = self.env['dvz.material.reservation'].search_count([
                ('project_id', '=', record.id)])

    def action_dvz_material_reservations(self):
        self.ensure_one()
        self.check_access('read')
        action = self.env['ir.actions.actions']._for_xml_id('dvz_material_reservation.action_material_reservations')
        action.update(domain=[('project_id', '=', self.id)], context={
            'default_project_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_company_id': (self.company_id or self.env.company).id,
        })
        return action


class AnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    dvz_material_reservation_count = fields.Integer(compute='_compute_dvz_material_count', compute_sudo=False, groups="stock.group_stock_user,sales_team.group_sale_salesman")

    def _compute_dvz_material_count(self):
        for record in self:
            record.dvz_material_reservation_count = self.env['dvz.material.reservation'].search_count([
                ('analytic_account_id', '=', record.id)])

    def action_dvz_material_reservations(self):
        self.ensure_one()
        self.check_access('read')
        action = self.env['ir.actions.actions']._for_xml_id('dvz_material_reservation.action_material_reservations')
        action.update(domain=[('analytic_account_id', '=', self.id)], context={
            'default_analytic_account_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_company_id': (self.company_id or self.env.company).id,
        })
        return action
