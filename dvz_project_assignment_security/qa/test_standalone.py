"""Executable without Odoo: tests policy logic and package structure, not live ORM."""
import ast
import importlib.util
import itertools
from pathlib import Path
import unittest
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dvz_policy', ROOT / 'policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def matches(domain, record):
    """Small evaluator for only the operators emitted by policy.py.

    This is not Odoo's SQL compiler and does not replace integration testing.
    """
    items = iter(domain)

    def one(item):
        if item in ('|', '&'):
            left = one(next(items)); right = one(next(items))
            return left or right if item == '|' else left and right
        if item == '!':
            return not one(next(items))
        field, operator, expected = item
        value = record.get(field, False)
        if operator == 'any!':
            related = value if isinstance(value, list) else [value] if value else []
            return any(matches(expected, child) for child in related)
        if operator == '=':
            return value == expected
        if operator == '!=':
            return value != expected
        if operator == 'in':
            return any(v in expected for v in value) if isinstance(value, list) else value in expected
        raise AssertionError('Unsupported operator: ' + operator)

    results = []
    for item in items:
        results.append(one(item))
    return all(results)


def project(manager=2, members=(), tasks=()):
    return {'user_id': manager, 'dvz_assigned_user_ids': list(members),
            'dvz_access_task_ids': list(tasks), 'company_id': 1}


def task(assignees=(), parent=False, company=1):
    return {'user_ids': list(assignees), 'project_id': parent, 'company_id': company}


class PolicyTests(unittest.TestCase):
    uid = 10

    def domain(self, scope, **kw):
        return policy.assignment_domain(self.uid, scope, [1], **kw)

    def test_only_assigned_task_is_visible(self):
        p = project()
        self.assertTrue(matches(self.domain('task'), task([10], p)))
        self.assertFalse(matches(self.domain('task'), task([20], p)))

    def test_assigned_project_grants_other_users_tasks(self):
        self.assertTrue(matches(self.domain('task'), task([20], project(manager=10))))

    def test_assigned_project_grants_unassigned_tasks(self):
        self.assertTrue(matches(self.domain('task'), task([], project(manager=10))))

    def test_native_project_manager_is_full_assignment(self):
        self.assertTrue(matches(self.domain('task'), task([20], project(manager=10))))

    def test_native_manager_can_read_empty_project(self):
        self.assertTrue(matches(self.domain('project_read'), project(manager=10)))

    def test_unassigned_empty_project_not_visible(self):
        self.assertFalse(matches(self.domain('project_read'), project()))

    def test_task_assignee_can_read_parent_header(self):
        self.assertTrue(matches(self.domain('project_read'), project(tasks=[task([10])])))

    def test_task_assignee_cannot_modify_parent_project(self):
        self.assertFalse(matches(self.domain('project_write'), project(tasks=[task([10])])))

    def test_follower_is_not_assignment(self):
        p = project(); p['message_partner_ids'] = [10]
        self.assertFalse(matches(self.domain('project_read'), p))

    def test_favorite_is_not_assignment(self):
        p = project(); p['favorite_user_ids'] = [10]
        self.assertFalse(matches(self.domain('project_read'), p))

    def test_all_employees_visibility_does_not_grant_access(self):
        for visibility in ['followers', 'employees', 'portal', 'invited_users']:
            p = project(); p['privacy_visibility'] = visibility
            self.assertFalse(matches(self.domain('project_read'), p))

    def test_task_in_other_company_does_not_grant_parent_header(self):
        self.assertFalse(matches(self.domain('project_read'), project(tasks=[task([10], company=2)])))

    def test_shared_company_task_grants_header(self):
        self.assertTrue(matches(self.domain('project_read'), project(tasks=[task([10], company=False)])))

    def test_hod_reads_all_projects(self):
        self.assertTrue(matches(self.domain('project_read', hod=True), project()))

    def test_hod_reads_all_project_tasks(self):
        self.assertTrue(matches(self.domain('task', hod=True), task([20], project())))

    def test_hod_not_granted_other_personal_tasks(self):
        self.assertFalse(matches(self.domain('task', hod=True), task([20])))

    def test_hod_keeps_own_personal_tasks(self):
        self.assertTrue(matches(self.domain('task', hod=True), task([10])))

    def test_ordinary_user_own_personal_task(self):
        self.assertTrue(matches(self.domain('task'), task([10])))
        self.assertFalse(matches(self.domain('task'), task([20])))

    def test_portal_guard_is_neutral(self):
        for scope in policy.SCOPES:
            self.assertEqual(self.domain(scope, portal=True), [])

    def test_settings_administrator_guard_is_neutral(self):
        for scope in policy.SCOPES:
            self.assertEqual(self.domain(scope, system=True), [])

    def test_task_only_user_cannot_read_project_updates(self):
        p = project(tasks=[task([10])])
        self.assertFalse(matches(self.domain('project_related'), {'project_id': p}))

    def test_full_project_user_reads_project_updates(self):
        self.assertTrue(matches(self.domain('project_related'), {'project_id': project(manager=10)}))

    def test_milestone_referenced_by_assigned_task(self):
        m = {'project_id': project(), 'task_ids': [task([10])]}
        self.assertTrue(matches(self.domain('milestone_read'), m))
        self.assertFalse(matches(self.domain('project_related'), m))

    def test_unrelated_milestone_denied(self):
        m = {'project_id': project(), 'task_ids': [task([20])]}
        self.assertFalse(matches(self.domain('milestone_read'), m))

    def test_burndown_uses_project_not_fabricated_task_ids(self):
        domain = self.domain('burndown')
        self.assertEqual(domain[0][0], 'project_id')
        self.assertTrue(matches(domain, {'project_id': project(tasks=[task([10])])}))
        self.assertFalse(matches(domain, {'project_id': project()}))

    def test_invalid_scope_is_rejected_even_for_admin(self):
        for kw in [{}, {'system': True}, {'hod': True}, {'portal': True}]:
            with self.assertRaises(ValueError):
                self.domain('invalid', **kw)

    def test_invalid_user_id_is_rejected(self):
        for uid in [0, -1, False, '10', None]:
            with self.assertRaises(ValueError):
                policy.assignment_domain(uid, 'task', [1])

    def test_no_mutable_domain_shared_between_calls(self):
        a = self.domain('task'); a.clear()
        self.assertNotEqual(self.domain('task'), [])

    def test_manager_change_changes_result_without_cached_id_lists(self):
        p = project(); t = task([20], p); d = self.domain('task')
        self.assertFalse(matches(d, t))
        p['user_id'] = 10
        self.assertTrue(matches(d, t))
        p['user_id'] = 20
        self.assertFalse(matches(d, t))

    def test_exhaustive_assignment_boolean_matrix(self):
        for project_manager, project_member, task_assignee in itertools.product([False, True], repeat=3):
            with self.subTest(project_manager=project_manager, member=project_member, task=task_assignee):
                p = project(manager=10 if project_manager else 20, members=[10] if project_member else [])
                t = task([10] if task_assignee else [20], p)
                self.assertEqual(matches(self.domain('task'), t), project_manager or task_assignee)

    def test_legacy_assignment_no_longer_grants_any_access(self):
        p = project(manager=20, members=[10])
        for scope in ('project_read', 'project_write'):
            self.assertFalse(matches(self.domain(scope), p))
        self.assertFalse(matches(self.domain('task'), task([20], p)))
        self.assertFalse(matches(self.domain('project_related'), {'project_id': p}))

    def test_other_task_assignees_do_not_grant_whole_project(self):
        p = project(tasks=[task([10]), task([20])])
        self.assertTrue(matches(self.domain('project_read'), p))
        self.assertFalse(matches(self.domain('task'), task([20], p)))


class PackageTests(unittest.TestCase):
    def test_manifest_data_exists(self):
        manifest = ast.literal_eval((ROOT / '__manifest__.py').read_text())
        self.assertEqual(manifest['depends'], ['project'])
        for filename in manifest['data']:
            self.assertTrue((ROOT / filename).is_file(), filename)

    def test_python_parses(self):
        for filename in ROOT.rglob('*.py'):
            ast.parse(filename.read_text(), filename=str(filename))

    def test_xml_parses(self):
        for filename in ROOT.rglob('*.xml'):
            etree.parse(str(filename))

    def test_global_guard_for_every_grant(self):
        tree = etree.parse(str(ROOT / 'security/project_rules.xml'))
        records = {r.get('id'): r for r in tree.xpath('//record')}
        self.assertEqual(len(records), 16)
        for rid, record in records.items():
            self.assertEqual(record.get('model'), 'ir.rule')
            if rid.endswith('_guard'):
                self.assertIsNone(record.find("field[@name='groups']"))
                grant = records[rid.replace('_guard', '_grant')]
                self.assertEqual(record.find("field[@name='domain_force']").text,
                                 grant.find("field[@name='domain_force']").text)

    def test_rule_expressions_use_only_known_scopes(self):
        tree = etree.parse(str(ROOT / 'security/project_rules.xml'))
        for f in tree.xpath("//field[@name='domain_force']"):
            expr = ast.parse(f.text, mode='eval').body
            self.assertIsInstance(expr, ast.Call)
            self.assertEqual(expr.func.attr, '_dvz_assignment_rule_domain')
            self.assertIn(expr.args[0].value, policy.SCOPES)

    def test_hod_group_implies_manager_not_system(self):
        xml = (ROOT / 'security/project_groups.xml').read_text()
        self.assertIn('project.group_project_manager', xml)
        self.assertNotIn('base.group_system', xml)
        self.assertIn('privilege_id', xml)

    def test_no_native_rule_is_deactivated_or_modified(self):
        tree = etree.parse(str(ROOT / 'security/project_rules.xml'))
        for record in tree.xpath('//record'):
            self.assertNotIn('.', record.get('id'))
            self.assertIsNone(record.find("field[@name='active']"))

    def test_no_custom_buttons_added(self):
        tree = etree.parse(str(ROOT / 'views/project_project_views.xml'))
        self.assertEqual(tree.xpath('//button'), [])

    def test_manager_role_renames_native_group_without_duplicate(self):
        tree = etree.parse(str(ROOT / 'security/project_groups.xml'))
        native = tree.xpath("//record[@id='project.group_project_manager']")
        self.assertEqual(len(native), 1)
        self.assertEqual(native[0].find("field[@name='name']").text, 'Project Manager')
        self.assertEqual(len(tree.xpath('//record')), 2)

    def test_no_legacy_field_in_views_or_policy(self):
        for file in (ROOT / 'views').glob('*.xml'):
            self.assertNotIn('dvz_assigned_user_ids', file.read_text())
        self.assertNotIn('dvz_assigned_user_ids', (ROOT / 'policy.py').read_text())

    def test_search_view_uses_standard_display_name(self):
        tree = etree.parse(str(ROOT / 'views/project_project_views.xml'))
        self.assertEqual(tree.xpath("//attribute[@name='filter_domain']/text()"),
                         ["[('display_name', 'ilike', self)]"])

    def test_migration_script_present_and_version_matches(self):
        manifest = ast.literal_eval((ROOT / '__manifest__.py').read_text())
        self.assertEqual(manifest['version'], '19.0.1.1.0')
        self.assertTrue((ROOT/'migrations'/manifest['version']/'post-migrate.py').is_file())
        self.assertEqual(manifest['uninstall_hook'], 'uninstall_hook')

    def test_legacy_storage_is_admin_only_and_readonly(self):
        tree = ast.parse((ROOT/'models/project_project.py').read_text())
        field = next(node.value for node in ast.walk(tree)
                     if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name)
                     and t.id == 'dvz_assigned_user_ids' for t in node.targets))
        keywords = {kw.arg: ast.literal_eval(kw.value) for kw in field.keywords}
        self.assertTrue(keywords['readonly'])
        self.assertEqual(keywords['groups'], 'base.group_system')

    def test_no_runtime_sudo_or_sql_is_used(self):
        for filename in (ROOT / 'models').glob('*.py'):
            tree = ast.parse(filename.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, {'sudo', 'execute', 'execute_query'})

    def test_no_new_acl_grants(self):
        self.assertFalse((ROOT / 'security/ir.model.access.csv').exists())

    def test_no_request_context_permission_bypass(self):
        for filename in (ROOT / 'models').glob('*.py'):
            self.assertNotIn('env.context.get', filename.read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
