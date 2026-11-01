"""Offline search/upgrade tests. Fakes below are NOT a live Odoo database."""
import base64
import csv
import importlib.util
import io
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = '_dvz_revision_offline'
package = ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package


def load(name):
    spec = importlib.util.spec_from_file_location(PACKAGE + '.' + name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


search = load('project_search')
plan = load('upgrade_plan')
migration = load('migration')
policy = load('policy')
hooks = load('hooks')


def evaluate(domain, record):
    if not domain:
        return True
    terms = iter(domain)
    def one(term):
        if term == '!':
            return not one(next(terms))
        if term in ('&', '|'):
            left, right = one(next(terms)), one(next(terms))
            return left and right if term == '&' else left or right
        field, op, value = term
        found = record.get(field, False)
        if op == 'ilike':
            return value.casefold() in str(found or '').casefold()
        if op == '=':
            return found == value
        if op == 'in':
            return any(x in value for x in found) if isinstance(found, list) else found in value
        if op == 'any!':
            relations = found if isinstance(found, list) else [found] if found else []
            return any(evaluate(value, obj) for obj in relations)
        raise AssertionError(op)
    results = [one(term) for term in terms]
    return all(results)


class SearchTests(unittest.TestCase):
    name = 'S00716 || ASD-TE-4128-VO'

    def match(self, query, operator='ilike', name=None):
        domain = search.project_name_domain(operator, query)
        self.assertIsNotNone(domain)
        return evaluate(domain, {'name': name or self.name})

    def test_each_component_and_numeric_fragment(self):
        for value in ('S00716', '00716', 'ASD', 'TE', '4128', 'VO'):
            with self.subTest(value=value):
                self.assertTrue(self.match(value))

    def test_multiple_parts_either_order(self):
        for value in ('ASD 4128', '4128 ASD', 'VO TE', 'S00716 ASD VO', 'VO 4128 TE ASD S00716'):
            with self.subTest(value=value):
                self.assertTrue(self.match(value))

    def test_case_insensitive(self):
        self.assertTrue(self.match('asd te vo'))

    def test_full_name(self):
        self.assertTrue(self.match(self.name))

    def test_full_code(self):
        self.assertTrue(self.match('ASD-TE-4128-VO'))

    def test_code_separators(self):
        for value in ('ASD/4128', 'ASD_4128', 'ASD.4128', 'ASD || 4128', 'ASD—4128', 'ASD\n4128'):
            self.assertTrue(self.match(value))

    def test_all_terms_must_match(self):
        self.assertFalse(self.match('ASD 9999'))
        self.assertFalse(self.match('TE ABC'))

    def test_terms_cannot_be_found_across_different_projects(self):
        self.assertFalse(self.match('ASD 4128', name='S00717 || ASD-TE-9999-VO'))
        self.assertFalse(self.match('ASD 4128', name='S00718 || BBB-EM-4128-VO'))

    def test_original_other_example(self):
        self.assertTrue(self.match('AIB EM 4128', name='S00642 || AIB-EM-4128-VO'))

    def test_plain_non_so_project(self):
        self.assertTrue(self.match('design office', name='Office Design Project'))

    def test_unicode_names(self):
        self.assertTrue(self.match('مشروع تركيب', name='مشروع تركيب النظام'))

    def test_leading_zeros_are_not_rewritten(self):
        self.assertEqual(search.project_name_tokens('S00716 0012'), ('S00716', '0012'))
        self.assertFalse(self.match('S716'))

    def test_zero_is_not_letter_o(self):
        self.assertFalse(self.match('V0'))
        self.assertTrue(self.match('V0', name='S00716 || ASD-TE-4128-V0'))

    def test_deduplicate_case_insensitively(self):
        self.assertEqual(search.project_name_tokens('ASD asd ASD 4128 4128'), ('ASD', '4128'))

    def test_negative_is_whole_expression_complement(self):
        self.assertFalse(self.match('ASD 4128', 'not ilike'))
        self.assertTrue(self.match('ASD 9999', 'not ilike'))
        self.assertTrue(self.match('XYZ 9999', 'not ilike'))

    def test_single_negative(self):
        self.assertFalse(self.match('ASD', 'not ilike'))
        self.assertTrue(self.match('XYZ', 'not ilike'))

    def test_native_operators_are_delegated(self):
        for op in ('=', '!=', 'in', 'not in', '=ilike', 'like', 'not like', '=like'):
            self.assertIsNone(search.project_name_domain(op, 'ASD'))

    def test_empty_and_non_text_delegate(self):
        for value in (False, None, 12, ['ASD'], '', '  ', '--- ||'):
            self.assertIsNone(search.project_name_domain('ilike', value))

    def test_no_domain_shared_between_calls(self):
        domain = search.project_name_domain('ilike', 'ASD 4128')
        domain.clear()
        self.assertTrue(self.match('ASD 4128'))

    def test_search_and_assignment_domain_intersect(self):
        name_domain = search.project_name_domain('ilike', 'ASD 4128')
        access_domain = policy.assignment_domain(10, 'project_read', [1])
        combined = ['&'] + name_domain + access_domain
        assigned = {'name': self.name, 'user_id': 10, 'dvz_access_task_ids': []}
        hidden = {'name': self.name, 'user_id': 20, 'dvz_access_task_ids': []}
        self.assertTrue(evaluate(combined, assigned))
        self.assertFalse(evaluate(combined, hidden))


class UpgradePlanTests(unittest.TestCase):
    def user(self, uid=10, **kw):
        return dict(id=uid, active=True, share=False, company_ok=True, **kw) if not kw else {
            **dict(id=uid, active=True, share=False, company_ok=True), **kw}

    def test_blank_manager_single_user_migrates(self):
        target, status, _ = plan.legacy_assignment_plan(False, [self.user()])
        self.assertEqual((target, status), (10, 'migrated'))

    def test_existing_same_manager_unchanged(self):
        target, status, _ = plan.legacy_assignment_plan(10, [self.user()])
        self.assertEqual((target, status), (None, 'already_native_manager'))

    def test_existing_different_manager_never_overwritten(self):
        target, status, _ = plan.legacy_assignment_plan(20, [self.user()])
        self.assertEqual((target, status), (None, 'review_existing_manager'))

    def test_multiple_users_never_arbitrarily_selected(self):
        target, status, _ = plan.legacy_assignment_plan(False, [self.user(), self.user(20)])
        self.assertEqual((target, status), (None, 'review_multiple_users'))

    def test_existing_manager_and_multiple_users_preserved(self):
        target, status, _ = plan.legacy_assignment_plan(20, [self.user(), self.user(20)])
        self.assertEqual((target, status), (None, 'review_existing_manager'))

    def test_archived_user_not_selected(self):
        self.assertEqual(plan.legacy_assignment_plan(False, [self.user(active=False)])[:2],
                         (None, 'review_ineligible_user'))

    def test_portal_user_not_selected(self):
        self.assertEqual(plan.legacy_assignment_plan(False, [self.user(share=True)])[:2],
                         (None, 'review_ineligible_user'))

    def test_company_not_granted_implicitly(self):
        self.assertEqual(plan.legacy_assignment_plan(False, [self.user(company_ok=False)])[:2],
                         (None, 'review_ineligible_user'))

    def test_no_legacy_data_no_change(self):
        for current in (False, 10):
            self.assertEqual(plan.legacy_assignment_plan(current, [])[:2],
                             (None, 'no_legacy_assignment'))

    def test_duplicate_input_user_id_does_not_create_ambiguity(self):
        self.assertEqual(plan.legacy_assignment_plan(False, [self.user(), self.user()])[0], 10)

    def test_no_mutation(self):
        users = [self.user()]
        before = [dict(u) for u in users]
        plan.legacy_assignment_plan(False, users)
        self.assertEqual(users, before)


class FakeUser:
    def __init__(self, uid=False, name=False, company=None, active=True, share=False):
        self.id, self.name, self.active, self.share = uid, name, active, share
        self.company_ids = [company] if company else []
    def __bool__(self):
        return bool(self.id)


class FakeProject:
    def __init__(self, pid, company, legacy, manager=None, name='S00716 || ASD-TE-4128-VO'):
        self.id, self.company_id, self.dvz_assigned_user_ids = pid, company, legacy
        self.user_id, self.name = manager or FakeUser(), name
        self.writes = []
        self.contexts = []
    def with_context(self, **context):
        self.contexts.append(context)
        return self
    def write(self, vals):
        self.writes.append(dict(vals))
        self.user_id = next(u for u in self.dvz_assigned_user_ids if u.id == vals['user_id'])
        return True


class FakeEnvironment:
    def __init__(self, projects):
        self.projects, self.attachments, self.contexts = projects, [], []
    def __getitem__(self, name):
        if name not in ('project.project', 'ir.attachment'):
            raise AssertionError(name)
        return self
    def with_context(self, **context):
        self.contexts.append(context)
        return self
    def search(self, domain, order=None):
        assert domain == [('dvz_assigned_user_ids', '!=', False)]
        assert order == 'id'
        return [p for p in self.projects if p.dvz_assigned_user_ids]
    def ref(self, name):
        assert name == 'base.module_dvz_project_assignment_security'
        return SimpleNamespace(id=777)
    def create(self, vals):
        self.attachments.append(vals)
        return SimpleNamespace(id=901)


class MigrationFunctionTests(unittest.TestCase):
    def setUp(self):
        self.company = SimpleNamespace(id=1, display_name='Aala Tech')
        self.user = FakeUser(10, 'Asad Aslam', self.company)
        self.other = FakeUser(20, 'Other Manager', self.company)

    def test_screenshot_scenario_writes_only_native_manager(self):
        project = FakeProject(100, self.company, [self.user])
        env = FakeEnvironment([project])
        result = migration.migrate_legacy_assignments(env)
        self.assertEqual(project.writes, [{'user_id': 10}])
        self.assertEqual(project.user_id.name, 'Asad Aslam')
        self.assertEqual(result, {'migrated': 1, 'review': 0, 'attachment_id': 901})
        self.assertEqual(project.dvz_assigned_user_ids, [self.user])

    def test_attachment_is_private_and_attached_to_admin_module_record(self):
        env = FakeEnvironment([FakeProject(100, self.company, [self.user])])
        migration.migrate_legacy_assignments(env)
        attachment = env.attachments[0]
        self.assertFalse(attachment['public'])
        self.assertEqual((attachment['res_model'], attachment['res_id']), ('ir.module.module', 777))
        self.assertNotIn('access_token', attachment)
        rows = list(csv.DictReader(io.StringIO(base64.b64decode(attachment['datas']).decode('utf-8-sig'))))
        self.assertEqual(rows[0]['Resulting Project Manager'], 'Asad Aslam')
        self.assertEqual(rows[0]['Status'], 'migrated')

    def test_conflicts_are_reported_without_modifying_project(self):
        project = FakeProject(100, self.company, [self.user], manager=self.other)
        env = FakeEnvironment([project])
        result = migration.migrate_legacy_assignments(env)
        self.assertEqual(project.writes, [])
        self.assertEqual(result['review'], 1)
        self.assertEqual(project.user_id, self.other)

    def test_multiple_assignees_are_reported_without_granting_access(self):
        project = FakeProject(100, self.company, [self.user, self.other])
        env = FakeEnvironment([project])
        result = migration.migrate_legacy_assignments(env)
        self.assertEqual(project.writes, [])
        self.assertFalse(project.user_id)
        self.assertEqual(result['review'], 1)

    def test_no_legacy_records_no_attachment(self):
        env = FakeEnvironment([])
        self.assertEqual(migration.migrate_legacy_assignments(env),
                         {'migrated': 0, 'review': 0, 'attachment_id': False})
        self.assertEqual(env.attachments, [])

    def test_repeat_run_does_not_reassign_manager(self):
        project = FakeProject(100, self.company, [self.user])
        env = FakeEnvironment([project])
        migration.migrate_legacy_assignments(env)
        result = migration.migrate_legacy_assignments(env)
        self.assertEqual(project.writes, [{'user_id': 10}])
        self.assertEqual(result['migrated'], 0)

    def test_archived_projects_are_included_in_upgrade_search(self):
        env = FakeEnvironment([])
        migration.migrate_legacy_assignments(env)
        self.assertIn({'active_test': False}, env.contexts)

    def test_csv_values_cannot_inject_spreadsheet_formula(self):
        for value in ('=1+1', '+123', '-123', '@SUM(A1)', '\t=1', '\n=1'):
            self.assertTrue(migration._csv_text(value).startswith("'"))
        self.assertEqual(migration._csv_text('S00716'), 'S00716')


class UninstallTests(unittest.TestCase):
    def group(self, name):
        class Group:
            def __init__(self, label):
                self.name = label
                self.writes = []
            def with_context(self, **kw):
                return self
            def write(self, vals):
                self.writes.append(vals)
        return Group(name)
    def test_native_label_restored_when_ours_still_active(self):
        group = self.group('Project Manager')
        env = SimpleNamespace(ref=lambda *args, **kw: group)
        hooks.uninstall_hook(env)
        self.assertEqual(group.writes[0]['name'], 'Administrator')
    def test_other_custom_label_not_overwritten(self):
        group = self.group('Operations Lead')
        env = SimpleNamespace(ref=lambda *args, **kw: group)
        hooks.uninstall_hook(env)
        self.assertEqual(group.writes, [])
    def test_missing_group_is_tolerated(self):
        hooks.uninstall_hook(SimpleNamespace(ref=lambda *args, **kw: False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
