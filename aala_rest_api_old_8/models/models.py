from odoo import models, fields, api

class System(models.Model):
    _name = 'system.master'
    _description = 'System Master'

    name = fields.Char(string='Name', required=True)
    image = fields.Binary()
    banner_image = fields.Binary()
    description = fields.Text(string='Description')
    division = fields.Many2one('division.master')
    url = fields.Char()



class Division(models.Model):
    _name = 'division.master'
    _description = 'Division Master'

    name = fields.Char(string='Name', required=True)


class Banner(models.Model):
    _name = 'banner.master'
    _description = 'Banner Master'

    image = fields.Binary(string='Banner Image')


class ProductBrand(models.Model):
    _name = 'product.brand'
    _description = 'Product Brand'

    name = fields.Char(string='Name', required=True)
    image = fields.Binary()
    banner_image = fields.Binary()
    description = fields.Text(string='Description')
    division = fields.Many2one('division.master')
    url = fields.Char()


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    _description = 'Sale Order'

    system = fields.Many2one('system.master')
    project = fields.Char()


class ProjectAppStage(models.Model):
    _name = 'project.app.stage'
    _description = 'Project App Stage'

    name = fields.Char()


class ProjectAppStatus(models.Model):
    _name = 'project.app.status'
    _description = 'Project App status'

    name = fields.Char()


class ProjectAppRemarks(models.Model):
    _name = 'project.app.remarks'
    _description = 'Project App Remarks'

    name = fields.Char()


class ProjectProject(models.Model):
    _inherit = 'project.project'

    project_status = fields.One2many('project.app.track', 'parent_id')
    system = fields.Many2one('system.master')
    team = fields.Many2one('project.team')


class ProjectAppTrack(models.Model):
    _name = 'project.app.track'

    parent_id = fields.Many2one('project.project')
    stage = fields.Many2one('project.app.stage')
    status = fields.Many2one('project.app.status')
    remarks = fields.Many2one('project.app.remarks')
    date = fields.Date()


class ProjectTeam(models.Model):
    _name = 'project.team'

    name = fields.Char()
    team_leader = fields.Many2one('hr.employee')
    team = fields.Many2many('hr.employee')


class AboutCompany(models.Model):
    _name = 'about.company'
    _description = 'About Company'

    name = fields.Char(string='Title', required=True)
    image = fields.Binary()
    description = fields.Text(string='Description')
    url = fields.Char()