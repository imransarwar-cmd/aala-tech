import ast
import unittest
from pathlib import Path
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]


class TestSystemDepartmentIntegration(unittest.TestCase):
    def test_manifest_depends_on_aala_rest_api(self):
        manifest = ast.literal_eval((ROOT / '__manifest__.py').read_text())
        self.assertIn('aala_rest_api', manifest['depends'])
        self.assertIn('views/system_master_views.xml', manifest['data'])

    def test_system_model_reused_not_recreated(self):
        source = (ROOT / 'models/system_master.py').read_text()
        self.assertIn("_inherit = 'system.master'", source)
        self.assertNotIn("_name = 'system.master'", source)
        self.assertIn("'dvz.sale.division'", source)

    def test_legacy_division_hidden_and_department_added(self):
        tree = etree.parse(str(ROOT / 'views/system_master_views.xml'))
        xml = etree.tostring(tree).decode()
        self.assertIn("//field[@name='division']", xml)
        self.assertIn('dvz_department_id', xml)

    def test_sales_orders_system_menu_after_department(self):
        tree = etree.parse(str(ROOT / 'views/system_master_views.xml'))
        menus = tree.xpath("//menuitem[@id='menu_systems_orders']")
        self.assertEqual(len(menus), 1)
        self.assertEqual(menus[0].get('parent'), 'sale.sale_order_menu')
        self.assertEqual(menus[0].get('sequence'), '26')
        self.assertEqual(menus[0].get('action'), 'aala_rest_api.action_system_master')

    def test_sale_order_system_domain_uses_department(self):
        source = (ROOT / 'models/sale_order.py').read_text()
        self.assertIn("[('dvz_department_id', '=', dvz_division_id)]", source)
        self.assertIn("def _onchange_dvz_department_system", source)
        self.assertIn("def _check_dvz_system_department", source)

    def test_department_display_is_name_and_label_is_abbreviation(self):
        source = (ROOT / 'models/division.py').read_text()
        self.assertIn("string='Abbreviation'", source)
        self.assertIn("division.display_name = division.name or ''", source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
