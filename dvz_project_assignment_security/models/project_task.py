from odoo import api, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    def _dvz_check_target_project(self, project_id):
        if project_id:
            self.env['project.project'].browse(project_id)._dvz_require_full_project_assignment()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.share and not self.env.user._dvz_can_administer_project_assignments():
            defaults = self.default_get(['project_id', 'parent_id'])
            for vals in vals_list:
                project_id = vals.get('project_id', defaults.get('project_id'))
                parent_id = vals.get('parent_id', defaults.get('parent_id'))
                if parent_id:
                    parent = self.browse(parent_id)
                    parent.check_access('read')
                    project_id = project_id or parent.project_id.id
                # Prevent self-granting access by creating a task in an otherwise
                # inaccessible project and assigning that new task to oneself.
                self._dvz_check_target_project(project_id)
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.user.share and not self.env.user._dvz_can_administer_project_assignments():
            # Check the ORIGINAL records before changing assignment or parent.
            self.check_access('write')
            if 'project_id' in vals:
                self._dvz_check_target_project(vals['project_id'])
                # Moving out also needs whole-project authority; a task-only
                # assignee cannot relocate a task to manufacture project access.
                self.mapped('project_id')._dvz_require_full_project_assignment()
            if vals.get('parent_id'):
                parent = self.browse(vals['parent_id'])
                parent.check_access('read')
                self._dvz_check_target_project(parent.project_id.id)
        return super().write(vals)
