"""Live Odoo 19 tests. INCLUDED BUT NOT EXECUTED in the build environment.

Run on a disposable staging DB with --test-tags /dvz_project_assignment_security.
These exercise actual ORM rules, unlike qa/test_standalone.py.
"""
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestAssignmentSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        defaults = {'company_id': company.id, 'company_ids': [Command.set(company.ids)]}
        cls.employee = new_test_user(cls.env, login='dvz_access_employee',
                                    groups='project.group_project_user', **defaults)
        cls.manager = new_test_user(cls.env, login='dvz_access_manager',
                                   groups='project.group_project_manager', **defaults)
        cls.other = new_test_user(cls.env, login='dvz_access_other',
                                 groups='project.group_project_user', **defaults)
        cls.hod = new_test_user(cls.env, login='dvz_access_hod',
                               groups='dvz_project_assignment_security.group_project_hod', **defaults)
        cls.portal = new_test_user(cls.env, login='dvz_access_portal', groups='base.group_portal', **defaults)
        Project = cls.env['project.project']
        cls.partial = Project.create({
            'name': 'DVZ Test: task assignments only', 'user_id': cls.other.id,
            'company_id': company.id, 'privacy_visibility': 'employees',
        })
        cls.full = Project.create({
            'name': 'DVZ Test: entire project assigned', 'user_id': cls.manager.id,
            'company_id': company.id, 'privacy_visibility': 'followers',
        })
        cls.hidden = Project.create({
            'name': 'DVZ Test: unrelated project', 'user_id': cls.other.id,
            'company_id': company.id, 'privacy_visibility': 'employees',
        })
        cls.native_managed = Project.create({
            'name': 'DVZ Test: native manager field', 'user_id': cls.manager.id,
            'company_id': company.id, 'privacy_visibility': 'followers',
        })
        Task = cls.env['project.task']
        def make(name, project, users):
            return Task.create({'name': name, 'project_id': project.id,
                                'user_ids': [Command.set(users.ids)]})
        cls.own = make('Assigned manager task', cls.partial, cls.manager)
        cls.employee_task = make('Assigned employee task', cls.partial, cls.employee)
        cls.sibling = make('Other assigned task', cls.partial, cls.other)
        cls.full_task = make('Whole-project task assigned to another user', cls.full, cls.other)
        cls.full_unassigned = make('Whole-project unassigned task', cls.full, cls.env['res.users'])
        cls.hidden_task = make('Unrelated task', cls.hidden, cls.other)
        cls.native_task = make('Native managed project task', cls.native_managed, cls.other)
        cls.all_projects = cls.partial | cls.full | cls.hidden | cls.native_managed
        cls.all_tasks = cls.own | cls.employee_task | cls.sibling | cls.full_task | cls.full_unassigned | cls.hidden_task | cls.native_task
        cls.env.flush_all()

    def as_user(self, records, user=None):
        return records.with_user(user or self.manager).sudo(False)

    def visible_tasks(self, user=None):
        return self.as_user(self.env['project.task'], user).search([('id', 'in', self.all_tasks.ids)])

    def test_manager_only_assigned_task_and_full_assigned_projects(self):
        expected = self.own | self.full_task | self.full_unassigned | self.native_task
        self.assertEqual(set(self.visible_tasks().ids), set(expected.ids))

    def test_regular_user_same_visibility_logic(self):
        expected = self.employee_task
        self.assertEqual(set(self.visible_tasks(self.employee).ids), set(expected.ids))

    def test_manager_can_read_task_parent_but_not_unrelated_project(self):
        self.as_user(self.partial).read(['name'])
        with self.assertRaises(AccessError):
            self.as_user(self.hidden).read(['name'])

    def test_direct_read_cannot_bypass_task_search_rules(self):
        with self.assertRaises(AccessError):
            self.as_user(self.sibling).read(['name', 'description'])

    def test_manager_native_see_all_rule_does_not_widen_scope(self):
        self.assertTrue(self.manager.has_group('project.group_project_manager'))
        self.assertFalse(self.as_user(self.hidden_task).has_access('read'))

    def test_task_only_can_edit_own_task(self):
        self.as_user(self.own).write({'name': 'Changed by assigned manager'})
        self.assertEqual(self.own.name, 'Changed by assigned manager')

    def test_task_only_cannot_modify_parent_project(self):
        with self.assertRaises(AccessError):
            self.as_user(self.partial).write({'description': '<p>Denied</p>'})

    def test_task_only_cannot_change_project_assignments(self):
        with self.assertRaises(AccessError):
            self.as_user(self.partial).write({'dvz_assigned_user_ids': [Command.link(self.manager.id)]})
        with self.assertRaises(AccessError):
            self.as_user(self.partial).write({'user_id': self.manager.id})

    def test_assigned_manager_still_cannot_change_project_security_fields(self):
        with self.assertRaises(AccessError):
            self.as_user(self.full).write({'dvz_assigned_user_ids': [Command.link(self.other.id)]})

    def test_hod_can_assign_project_and_revocation_takes_effect(self):
        # Warm the normal record-rule cache before changing membership.
        self.assertNotIn(self.hidden_task.id, self.visible_tasks().ids)
        self.as_user(self.hidden, self.hod).write({'user_id': self.manager.id})
        self.assertIn(self.hidden_task.id, self.visible_tasks().ids)
        self.as_user(self.hidden, self.hod).write({'user_id': self.other.id})
        self.assertNotIn(self.hidden_task.id, self.visible_tasks().ids)

    def test_hod_sees_all_project_tasks(self):
        self.assertEqual(set(self.visible_tasks(self.hod).ids), set(self.all_tasks.ids))
        records = self.as_user(self.env['project.project'], self.hod).search([('id', 'in', self.all_projects.ids)])
        self.assertEqual(set(records.ids), set(self.all_projects.ids))

    def test_hod_cannot_see_other_users_projectless_personal_tasks(self):
        personal = self.env['project.task'].create({
            'name': 'Other user private task', 'project_id': False,
            'user_ids': [Command.set(self.other.ids)],
        })
        with self.assertRaises(AccessError):
            self.as_user(personal, self.hod).read(['name'])

    def test_following_does_not_grant_unrelated_project_or_tasks(self):
        self.hidden.message_subscribe(partner_ids=self.manager.partner_id.ids)
        self.hidden_task.message_subscribe(partner_ids=self.manager.partner_id.ids)
        self.assertFalse(self.as_user(self.hidden).has_access('read'))
        self.assertFalse(self.as_user(self.hidden_task).has_access('read'))

    def test_native_project_manager_sees_all_its_tasks(self):
        self.assertTrue(self.as_user(self.native_task).has_access('read'))

    def test_assigned_project_gives_access_to_future_unassigned_tasks(self):
        created = self.env['project.task'].create({'name': 'Future task', 'project_id': self.full.id})
        self.assertTrue(self.as_user(created).has_access('read'))

    def test_task_creation_cannot_be_used_to_grant_access(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.as_user(self.env['project.task']).create({
                'name': 'Attempt self assignment', 'project_id': self.hidden.id,
                'user_ids': [Command.set(self.manager.ids)],
            })

    def test_context_defaults_cannot_bypass_creation_guard(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.as_user(self.env['project.task']).with_context(
                default_project_id=self.hidden.id,
                default_user_ids=[Command.set(self.manager.ids)],
            ).create({'name': 'Attempt through context'})

    def test_task_move_cannot_be_used_to_grant_access(self):
        with self.assertRaises(AccessError):
            self.as_user(self.own).write({'project_id': self.hidden.id})
        self.assertEqual(self.own.project_id, self.partial)

    def test_manager_can_create_tasks_in_fully_assigned_project(self):
        created = self.as_user(self.env['project.task']).create({
            'name': 'Normal project task', 'project_id': self.full.id,
        })
        self.assertTrue(self.as_user(created).has_access('read'))

    def test_completed_task_still_grants_parent_read(self):
        self.own.state = '1_done'
        self.employee_task.user_ids = False
        self.assertTrue(self.as_user(self.partial).has_access('read'))

    def test_archived_task_still_grants_parent_read(self):
        self.own.active = False
        self.assertTrue(self.as_user(self.partial).has_access('read'))
        self.assertTrue(self.as_user(self.own).with_context(active_test=False).has_access('read'))

    def test_task_analysis_applies_same_assignments(self):
        reports = self.as_user(self.env['report.project.task.user']).search([('task_id', 'in', self.all_tasks.ids)])
        expected = self.own | self.full_task | self.full_unassigned | self.native_task
        self.assertEqual(set(reports.task_id.ids), set(expected.ids))

    def test_burndown_query_runs_without_aggregate_task_id_join(self):
        # Requires actual Odoo SQL compilation; cannot be validated standalone.
        self.as_user(self.env['project.task.burndown.chart.report'])._read_group(
            [('project_id', 'in', self.all_projects.ids)],
            groupby=['date:month', 'stage_id', 'project_id'], aggregates=['__count'],
        )

    def test_task_only_dashboard_is_empty(self):
        self.assertEqual(self.as_user(self.partial).get_panel_data(), {})
        with self.assertRaises(AccessError):
            self.as_user(self.partial).project_update_all_action()

    def test_unrelated_project_dashboard_direct_rpc_denied(self):
        with self.assertRaises(AccessError):
            self.as_user(self.hidden).get_panel_data()

    def test_assignment_does_not_make_regular_user_project_administrator(self):
        self.assertFalse(self.employee.has_group('project.group_project_manager'))
        with self.assertRaises(AccessError):
            self.as_user(self.full, self.employee).write({'name': 'Not permitted by native ACL'})

    def test_portal_user_not_accepted_as_project_manager(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.full.write({'user_id': self.portal.id})

    def test_native_company_boundary_still_applies_to_hod(self):
        foreign_company = self.env['res.company'].create({'name': 'DVZ Other Company'})
        foreign_project = self.env['project.project'].sudo().create({
            'name': 'Another company', 'company_id': foreign_company.id, 'user_id': False,
        })
        with self.assertRaises(AccessError):
            self.as_user(foreign_project, self.hod).with_context(
                allowed_company_ids=[self.env.company.id]
            ).read(['name'])

    def test_portal_rule_helper_is_neutral(self):
        domain = self.portal._dvz_assignment_rule_domain('task', [self.env.company.id])
        self.assertTrue(domain.is_true())

    def test_view_inheritance_compiles(self):
        view = self.as_user(self.env['project.project']).get_view(
            view_id=self.env.ref('project.edit_project').id, view_type='form')
        self.assertNotIn('dvz_assigned_user_ids', view['arch'])
        self.assertIn('user_id', view['arch'])

    def test_manager_role_has_requested_label(self):
        group = self.env.ref('project.group_project_manager').with_context(lang='en_US')
        self.assertEqual(group.name, 'Project Manager')

    def test_regular_user_native_project_assignment_gives_all_tasks(self):
        self.full.write({'user_id': self.employee.id})
        visible = set(self.visible_tasks(self.employee).ids)
        self.assertIn(self.full_task.id, visible)
        self.assertIn(self.full_unassigned.id, visible)
        self.assertFalse(self.employee.has_group('project.group_project_manager'))

    def test_project_search_each_component_and_multiple_terms(self):
        self.full.name = 'S00716 || ASD-TE-4128-VO'
        Project = self.as_user(self.env['project.project'])
        for query in ('S00716', '00716', 'ASD', 'TE', '4128', 'VO',
                      'asd 4128', '4128 ASD', 'S00716 VO',
                      'S00716 || ASD-TE-4128-VO'):
            with self.subTest(query=query):
                found = Project.search([('display_name', 'ilike', query),
                                        ('id', 'in', self.all_projects.ids)])
                self.assertIn(self.full, found)
                self.assertIn(self.full.id, dict(Project.name_search(query)))

    def test_project_search_keeps_record_rule_restrictions(self):
        self.hidden.name = 'S00716 || ASD-TE-4128-VO'
        self.full.name = 'S00716 || ASD-TE-4128-VO'
        Project = self.as_user(self.env['project.project'])
        self.assertEqual(set(Project.search([('display_name', 'ilike', 'ASD 4128')]).ids),
                         {self.full.id})
        self.assertNotIn(self.hidden.id, dict(Project.name_search('ASD 4128')))

    def test_project_search_wrong_combination_does_not_match(self):
        self.full.name = 'S00716 || ASD-TE-4128-VO'
        found = self.as_user(self.env['project.project']).search([
            ('id', '=', self.full.id), ('display_name', 'ilike', 'ASD 9999')])
        self.assertFalse(found)

    def test_project_search_preserves_explicit_domain(self):
        self.full.name = 'S00716 || ASD-TE-4128-VO'
        found = self.as_user(self.env['project.project']).name_search(
            'ASD 4128', domain=[('id', '!=', self.full.id)])
        self.assertNotIn(self.full.id, dict(found))

    def test_project_search_exact_equality_stays_exact(self):
        self.full.name = 'S00716 || ASD-TE-4128-VO'
        Project = self.as_user(self.env['project.project'])
        self.assertNotIn(self.full.id, dict(Project.name_search('ASD', operator='=')))
        self.assertIn(self.full.id, dict(Project.name_search(self.full.name, operator='=')))

    def test_project_search_not_ilike_is_complement(self):
        self.full.name = 'S00716 || ASD-TE-4128-VO'
        found = self.as_user(self.env['project.project']).search([
            ('id', '=', self.full.id), ('display_name', 'not ilike', 'ASD 4128')])
        self.assertFalse(found)
        found = self.as_user(self.env['project.project']).search([
            ('id', '=', self.full.id), ('display_name', 'not ilike', 'ASD 9999')])
        self.assertEqual(found, self.full)

    def test_archived_project_needs_native_archived_filter(self):
        self.full.name = 'S00716 || ASD-TE-4128-VO'
        self.full.active = False
        Project = self.as_user(self.env['project.project'])
        self.assertNotIn(self.full.id, dict(Project.name_search('ASD 4128')))
        self.assertIn(self.full.id, dict(Project.with_context(active_test=False).name_search('ASD 4128')))

    def test_hod_can_leave_project_manager_blank(self):
        self.as_user(self.full, self.hod).write({'user_id': False})
        self.assertFalse(self.as_user(self.full_task).has_access('read'))
        self.assertTrue(self.as_user(self.full_task, self.hod).has_access('read'))

    def _seed_legacy_assignment_for_upgrade_test(self, project, user):
        # Simulate pre-upgrade historical data. Production migration does not
        # use raw SQL and public create/write deliberately reject this field.
        self.env.cr.execute(
            "INSERT INTO dvz_project_assigned_user_rel (project_id, user_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING", (project.id, user.id))
        project.invalidate_recordset(['dvz_assigned_user_ids'])

    def test_legacy_storage_alone_grants_no_visibility(self):
        self._seed_legacy_assignment_for_upgrade_test(self.hidden, self.manager)
        self.assertFalse(self.as_user(self.hidden_task).has_access('read'))
        self.assertFalse(self.as_user(self.hidden).has_access('read'))

    def test_legacy_storage_is_not_readable_by_ordinary_manager(self):
        self._seed_legacy_assignment_for_upgrade_test(self.full, self.manager)
        with self.assertRaises(AccessError):
            self.as_user(self.full).read(['dvz_assigned_user_ids'])

    def test_upgrade_moves_sole_user_into_empty_native_manager(self):
        from ..migration import migrate_legacy_assignments
        self.full.write({'user_id': False})
        self._seed_legacy_assignment_for_upgrade_test(self.full, self.manager)
        self.assertFalse(self.as_user(self.full_task).has_access('read'))
        result = migrate_legacy_assignments(self.env)
        self.assertEqual(self.full.user_id, self.manager)
        self.assertTrue(self.as_user(self.full_task).has_access('read'))
        self.assertTrue(result['attachment_id'])

    def test_upgrade_does_not_overwrite_existing_manager(self):
        from ..migration import migrate_legacy_assignments
        self._seed_legacy_assignment_for_upgrade_test(self.full, self.other)
        migrate_legacy_assignments(self.env)
        self.assertEqual(self.full.user_id, self.manager)

    def test_upgrade_does_not_choose_arbitrary_manager(self):
        from ..migration import migrate_legacy_assignments
        self.full.write({'user_id': False})
        self._seed_legacy_assignment_for_upgrade_test(self.full, self.manager)
        self._seed_legacy_assignment_for_upgrade_test(self.full, self.other)
        migrate_legacy_assignments(self.env)
        self.assertFalse(self.full.user_id)

    def test_upgrade_report_not_readable_by_ordinary_manager(self):
        from ..migration import migrate_legacy_assignments
        self._seed_legacy_assignment_for_upgrade_test(self.full, self.manager)
        result = migrate_legacy_assignments(self.env)
        attachment = self.env['ir.attachment'].browse(result['attachment_id'])
        self.assertFalse(attachment.public)
        with self.assertRaises(AccessError):
            self.as_user(attachment).read(['datas'])
