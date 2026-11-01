from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from ..project_search import project_name_domain


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # Compatibility storage only. Removed from all views and access policies.
    # Keep old data for a safe, auditable upgrade; never use it to grant access.
    dvz_assigned_user_ids = fields.Many2many(
        'res.users', 'dvz_project_assigned_user_rel', 'project_id', 'user_id',
        string='Legacy Project Assignments (Unused)', copy=False, readonly=True,
        groups='base.group_system',
        help='Historical assignments from version 19.0.1.0.0. This field grants '
             'NO access. Use the existing Project Manager field instead.',
    )
    dvz_access_task_ids = fields.One2many(
        'project.task', 'project_id', string='Tasks for Access Evaluation',
        readonly=True, context={'active_test': False},
        help='Unfiltered relation used by assignment rules, including completed '
             'and archived tasks. This is not a separate assignment field.',
    )
    dvz_can_assign_project = fields.Boolean(compute='_compute_dvz_access_flags')
    dvz_has_full_project_access = fields.Boolean(compute='_compute_dvz_access_flags')

    @api.depends_context('uid')
    @api.depends('user_id')
    def _compute_dvz_access_flags(self):
        elevated = self.env.user._dvz_can_administer_project_assignments()
        for project in self:
            project.dvz_can_assign_project = elevated
            project.dvz_has_full_project_access = elevated or (
                project.user_id.id == self.env.uid
            )

    def _dvz_require_full_project_assignment(self):
        """Private guard for moving/creating tasks; no context bypass switch."""
        self.check_access('read')
        if self.env.user._dvz_can_administer_project_assignments():
            return
        if any(project.user_id.id != self.env.uid for project in self):
            raise AccessError(_(
                'This operation requires assignment to the whole project. '
                'A task assignment alone does not grant project administration.'
            ))

    @api.model
    def _search_display_name(self, operator, value):
        # Native project selectors use display_name. Return a domain, not a
        # sudo search or a precomputed ID list, so all record rules still apply.
        domain = project_name_domain(operator, value)
        if domain is not None:
            return domain
        return super()._search_display_name(operator, value)

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('dvz_assigned_user_ids') for vals in vals_list):
            raise AccessError(_(
                'Assigned Project Users is no longer used. '
                'Select the responsible person in Project Manager.'
            ))
        if not self.env.user._dvz_can_administer_project_assignments():
            # The native Project Manager can create projects for themselves,
            # but cannot assign others through imports or default context.
            defaults = self.default_get(['user_id'])
            for vals in vals_list:
                manager = vals.get('user_id', defaults.get('user_id'))
                if manager != self.env.uid:
                    raise AccessError(_(
                        'Only an HOD or Settings Administrator may assign a '
                        'project to another person. Create the project for '
                        'yourself, then ask the HOD to change its Project Manager.'
                    ))
        return super().create(vals_list)

    def write(self, vals):
        if 'dvz_assigned_user_ids' in vals:
            raise AccessError(_(
                'Legacy project assignments are retained for upgrade audit only. '
                'Use the existing Project Manager field.'
            ))
        if 'user_id' in vals:
            if not self.env.user._dvz_can_administer_project_assignments():
                raise AccessError(_(
                    'Only an HOD or Settings Administrator may change '
                    'the Project Manager.'
                ))
        return super().write(vals)

    @api.constrains('user_id', 'company_id')
    def _check_dvz_project_manager(self):
        for project in self:
            user = project.user_id
            if not user:
                continue
            if user.share:
                raise ValidationError(_('The Project Manager must be an internal user.'))
            if project.company_id and project.company_id not in user.company_ids:
                raise ValidationError(_(
                    'The Project Manager must have access to the project company.'
                ))

    def project_update_all_action(self):
        # A task-only assignee can read the parent project header, but may not
        # enter the full-project dashboard (which may contain financial data).
        self._dvz_require_full_project_assignment()
        return super().project_update_all_action()

    def get_panel_data(self):
        self.ensure_one()
        self.check_access('read')
        # The task board may fetch this method automatically. Return an empty
        # dashboard for task-only assignees rather than blocking their task UI.
        if not self.env.user.share and not self.dvz_has_full_project_access:
            return {}
        return super().get_panel_data()

    def action_profitability_items(self, section_name, domain=None, res_id=False):
        self._dvz_require_full_project_assignment()
        return super().action_profitability_items(section_name, domain=domain, res_id=res_id)

    def action_open_share_project_wizard(self):
        self._dvz_require_full_project_assignment()
        return super().action_open_share_project_wizard()
