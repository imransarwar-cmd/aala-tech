"""Standalone checks; do NOT claim these exercise the Odoo ORM or browser."""
import ast
import csv
import importlib.util
from pathlib import Path
import unittest
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dvz_naming_pure', ROOT / 'naming.py')
naming = importlib.util.module_from_spec(spec)
spec.loader.exec_module(naming)


class TestNaming(unittest.TestCase):
    def test_requested_example(self):
        self.assertEqual(naming.make_project_code('AIB', 'EM', '4128', 'VO'), 'AIB-EM-4128-VO')

    def test_combined_name(self):
        self.assertEqual(naming.make_project_name('S00642', 'AIB-EM-4128-VO'),
                         'S00642 || AIB-EM-4128-VO')

    def test_code_only(self):
        self.assertEqual(naming.make_project_name('S00642', 'AIB-EM-4128-VO', False),
                         'AIB-EM-4128-VO')

    def test_optional_suffix(self):
        self.assertEqual(naming.make_project_code('AIB', 'EM', '4128'), 'AIB-EM-4128')

    def test_false_suffix(self):
        self.assertEqual(naming.make_project_code('AIB', 'EM', '4128', False), 'AIB-EM-4128')

    def test_trim_and_uppercase(self):
        self.assertEqual(naming.make_project_code(' aib ', ' em ', ' 4128 ', ' vo '), 'AIB-EM-4128-VO')

    def test_leading_zeroes(self):
        self.assertEqual(naming.make_project_code('AIB', 'EM', '004128'), 'AIB-EM-004128')

    def test_reference_separators(self):
        self.assertEqual(naming.make_project_code('AIB', 'EM', 'PRJ/2026-4128'), 'AIB-EM-PRJ/2026-4128')

    def test_missing_salesperson(self):
        with self.assertRaises(ValueError):
            naming.make_project_code(False, 'EM', '4128')

    def test_missing_division(self):
        with self.assertRaises(ValueError):
            naming.make_project_code('AIB', '', '4128')

    def test_missing_reference(self):
        with self.assertRaises(ValueError):
            naming.make_project_code('AIB', 'EM', None)

    def test_invalid_spaces(self):
        with self.assertRaises(ValueError):
            naming.make_project_code('A IB', 'EM', '4128')

    def test_invalid_markup(self):
        with self.assertRaises(ValueError):
            naming.make_project_code('<AIB>', 'EM', '4128')

    def test_invalid_division_separator(self):
        with self.assertRaises(ValueError):
            naming.make_project_code('AIB', 'E-M', '4128')

    def test_invalid_reference(self):
        with self.assertRaises(ValueError):
            naming.make_project_code('AIB', 'EM', '../4128')

    def test_invalid_suffix(self):
        with self.assertRaises(ValueError):
            naming.make_project_code('AIB', 'EM', '4128', 'VO 1')

    def test_integer_reference_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            naming.make_project_code('AIB', 'EM', 4128)

    def test_length_limits(self):
        with self.assertRaises(ValueError):
            naming.make_project_code('A'*17, 'EM', '4128')
        with self.assertRaises(ValueError):
            naming.make_project_code('AIB', 'EM', '1'*41)

    def test_missing_order_number(self):
        with self.assertRaises(ValueError):
            naming.make_project_name(False, 'AIB-EM-4128')

    def test_blank_code_no_partial_name(self):
        self.assertEqual(naming.make_project_name('S00642', False), '')


class TestPackage(unittest.TestCase):
    def test_python_syntax(self):
        for path in ROOT.rglob('*.py'):
            with self.subTest(path=path.relative_to(ROOT)):
                ast.parse(path.read_text(), filename=str(path))

    def test_manifest_files_exist(self):
        manifest = ast.literal_eval((ROOT/'__manifest__.py').read_text())
        self.assertTrue(manifest['installable'])
        self.assertEqual(manifest['version'], '19.0.1.2.0')
        self.assertIn('sale_project', manifest['depends'])
        for name in manifest['data']:
            self.assertTrue((ROOT/name).is_file(), name)

    def test_xml_parses(self):
        for path in ROOT.rglob('*.xml'):
            with self.subTest(path=path.relative_to(ROOT)):
                tree = etree.parse(str(path))
                self.assertEqual(tree.getroot().tag, 'odoo')

    def test_no_new_smart_buttons(self):
        for path in (ROOT/'views').glob('*.xml'):
            tree = etree.parse(str(path))
            self.assertFalse(tree.xpath('//button[contains(@class, "oe_stat_button")]'))

    def test_division_first_in_project_information(self):
        tree = etree.parse(str(ROOT/'views/sale_order_views.xml'))
        fields = tree.xpath("//group[@name='dvz_project_information_left']/field")
        self.assertEqual([f.get('name') for f in fields], ['dvz_division_id'])
        self.assertEqual(len(tree.xpath("//record[@id='sale_order_form_project_naming']//field[@name='dvz_division_id']")), 1)
        self.assertFalse(tree.xpath("//group[@name='dvz_project_naming']//field[@name='dvz_division_id']"))

    def test_acl_no_portal_or_global_write(self):
        with (ROOT/'security/ir.model.access.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertTrue(rows)
        for row in rows:
            self.assertTrue(row['group_id:id'])
            self.assertNotIn('portal', row['group_id:id'])
        reader = next(r for r in rows if r['group_id:id'] == 'base.group_user')
        self.assertEqual((reader['perm_read'], reader['perm_write'], reader['perm_create']), ('1','0','0'))

    def test_multi_company_rule(self):
        tree = etree.parse(str(ROOT/'security/division_security.xml'))
        domain = tree.xpath('//field[@name="domain_force"]/text()')[0]
        self.assertIn('company_ids', domain)
        self.assertIn('company_id', domain)

    def test_native_project_creation_not_reimplemented(self):
        # This add-on never explicitly calls env['project.project'].create().
        for path in (ROOT/'models').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'create':
                    self.assertNotEqual(ast.unparse(node.func.value), "self.env['project.project']")

    def test_native_project_hooks_call_super(self):
        src = (ROOT/'models/sale_order_line.py').read_text()
        self.assertIn('super()._timesheet_create_project_prepare_values()', src)
        self.assertIn('super()._timesheet_create_project()', src)

    def test_no_invoice_or_accounting_model_override(self):
        for path in (ROOT/'models').glob('*.py'):
            src = path.read_text()
            self.assertNotIn("_inherit = 'account.move'", src)
            self.assertNotIn("_inherit = 'account.move.line'", src)

    def test_odoo19_constraint_api(self):
        src = (ROOT/'models/division.py').read_text()
        self.assertIn('models.Constraint(', src)
        self.assertNotIn('_sql_constraints', src)

    def test_module_imports_exist(self):
        for name in ('division','res_users','sale_order','sale_order_line','project_project'):
            self.assertTrue((ROOT/'models'/f'{name}.py').exists())
            self.assertIn(f'from . import {name}', (ROOT/'models/__init__.py').read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
