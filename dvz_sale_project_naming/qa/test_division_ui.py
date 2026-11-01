"""Static contract checks for the division menus, mail integration and views."""
import ast
from pathlib import Path
import unittest
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]


class TestDivisionUI(unittest.TestCase):
    def setUp(self):
        self.division_xml = etree.parse(str(ROOT/'views/division_views.xml'))
        self.sale_xml = etree.parse(str(ROOT/'views/sale_order_views.xml'))
        self.division_source = (ROOT/'models/division.py').read_text()

    def test_both_menus_open_same_action(self):
        menus = self.division_xml.xpath('//menuitem')
        self.assertEqual(len(menus), 2)
        self.assertEqual({m.get('action') for m in menus}, {'action_divisions'})
        self.assertEqual({m.get('parent') for m in menus}, {'sale.menu_sale_config','sale.sale_order_menu'})

    def test_sales_orders_menu_available_to_salespeople(self):
        node = self.division_xml.xpath("//menuitem[@id='menu_divisions_orders']")[0]
        self.assertIn('sales_team.group_sale_salesman', node.get('groups').split(','))

    def test_original_configuration_menu_id_retained(self):
        self.assertEqual(len(self.division_xml.xpath("//menuitem[@id='menu_divisions']")), 1)

    def test_master_model_not_renamed(self):
        self.assertIn("_name = 'dvz.sale.division'", self.division_source)
        self.assertEqual(self.division_xml.xpath("//record[@id='action_divisions']/field[@name='res_model']/text()"), ['dvz.sale.division'])

    def test_mail_and_activity_mixins_present(self):
        self.assertIn("_inherit = ['mail.thread', 'mail.activity.mixin']", self.division_source)
        manifest = ast.literal_eval((ROOT/'__manifest__.py').read_text())
        self.assertIn('mail', manifest['depends'])

    def test_one_division_chatter_outside_sheet(self):
        self.assertEqual(len(self.division_xml.xpath('//form/chatter')), 1)
        self.assertFalse(self.division_xml.xpath('//sheet//chatter'))

    def test_no_second_sale_order_chatter_added(self):
        self.assertFalse(self.sale_xml.xpath('//chatter'))

    def test_chatter_posting_does_not_grant_master_write(self):
        self.assertIn("_mail_post_access = 'read'", self.division_source)
        self.assertNotIn('message_post(', self.division_source)
        self.assertNotIn('mail.message', self.division_source)

    def test_key_master_fields_tracked(self):
        tree = ast.parse(self.division_source)
        klass = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        fields = {n.targets[0].id: n.value for n in klass.body
                  if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                  and isinstance(n.value, ast.Call)}
        for name in ('name','code','company_id','active'):
            with self.subTest(field=name):
                options = {kw.arg: kw.value for kw in fields[name].keywords}
                self.assertTrue(ast.literal_eval(options['tracking']))

    def test_division_activity_column(self):
        self.assertEqual(len(self.division_xml.xpath('//list/field[@name="activity_ids"][@widget="list_activity"]')), 1)

    def test_so_group_by_uses_existing_division_field(self):
        node = self.sale_xml.xpath('//filter[@name="dvz_group_by_division"]')[0]
        self.assertEqual(ast.literal_eval(node.get('context')), {'group_by': 'dvz_division_id'})

    def test_project_naming_section_separate_from_project_information(self):
        parent = self.sale_xml.xpath('//group[@name="dvz_project_naming"]')[0].getparent()
        self.assertEqual(parent.tag, 'xpath')
        self.assertEqual(parent.get('expr'), "//page[@name='other_information']")
        self.assertFalse(self.sale_xml.xpath('//group[@name="dvz_project_information"]//field[@name="dvz_project_reference"]'))

    def test_combined_view_transform_before_odoo_postprocessing(self):
        source = (ROOT/'models/sale_order.py').read_text()
        self.assertIn("def _get_view(self, view_id=None, view_type='form', **options):", source)
        self.assertIn('super()._get_view(view_id, view_type, **options)', source)
        self.assertIn('arch = deepcopy(arch)', source)
        method = source[source.index('    def _get_view('):]
        self.assertNotIn('self.env.user', method)
        self.assertNotIn('has_group(', method)
        self.assertNotIn('fields_get(', method.replace('not fields_get()', ''))

    def test_no_schema_for_duplicate_custom_fields(self):
        source = (ROOT/'models/sale_order.py').read_text()
        for field in ('x_system', 'x_project', 'x_brand', 'x_area', 'x_priority', 'x_remarks', 'x_logo'):
            self.assertNotIn(f'{field} = fields.', source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
