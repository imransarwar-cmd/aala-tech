"""Odoo integration tests. Run on a disposable Odoo 19 database, not production."""
from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.addons.sale_project.tests.common import TestSaleProjectCommon


@tagged('post_install', '-at_install')
class TestSaleProjectNaming(TestSaleProjectCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.dvz_sales_abbreviation = 'AIB'
        cls.naming_partner = cls.env['res.partner'].create({'name': 'Project Naming Test Customer'})
        cls.division = cls.env['dvz.sale.division'].create({
            'name': 'Test Division', 'code': ' em ', 'company_id': cls.env.company.id,
        })

    def _order(self, product=None, naming=True, **extra):
        product = product or self.product_delivery_manual4
        vals = {
            'partner_id': self.naming_partner.id,
            'user_id': self.env.user.id,
            'company_id': self.env.company.id,
            'order_line': [Command.create({
                'product_id': product.id,
                'name': product.name,
                'product_uom_qty': 1,
                'price_unit': 100,
            })],
        }
        if naming:
            vals.update({
                'dvz_division_id': self.division.id,
                'dvz_project_reference': '4128',
                'dvz_project_suffix': 'VO',
            })
        vals.update(extra)
        return self.env['sale.order'].create(vals)

    def test_code_and_default_name(self):
        order = self._order(name='S00642')
        self.assertEqual(order.dvz_project_code, 'AIB-EM-4128-VO')
        self.assertEqual(order.dvz_project_name, 'S00642 || AIB-EM-4128-VO')

    def test_native_project_creation_name_links_and_order_unchanged(self):
        order = self._order(name='S00642')
        order.action_confirm()
        project = order.order_line.project_id
        self.assertEqual(len(project), 1)
        self.assertEqual(order.name, 'S00642')
        self.assertEqual(project.name, 'S00642 || AIB-EM-4128-VO')
        self.assertEqual(project.sale_order_id, order)
        self.assertEqual(project.dvz_origin_sale_id, order)
        self.assertEqual(project.dvz_division_id, self.division)
        self.assertIn(project, order.project_ids)

    def test_optional_suffix(self):
        order = self._order(dvz_project_suffix=False)
        order.action_confirm()
        self.assertEqual(order.order_line.project_id.dvz_project_code, 'AIB-EM-4128')
        self.assertFalse(order.order_line.project_id.name.endswith('-'))

    def test_code_only(self):
        order = self._order(dvz_include_so_number=False)
        order.action_confirm()
        self.assertEqual(order.order_line.project_id.name, 'AIB-EM-4128-VO')

    def test_template_name_not_appended(self):
        original_template_name = self.project_template.name
        order = self._order(self.product_delivery_manual5)
        order.action_confirm()
        self.assertEqual(order.order_line.project_id.name, order.dvz_project_name)
        self.assertEqual(self.project_template.name, original_template_name)
        self.assertNotEqual(order.order_line.project_id, self.project_template)

    def test_new_style_template(self):
        template = self.env['project.project'].create({
            'name': 'Example Actual Template', 'is_template': True,
            'allow_billable': True, 'company_id': self.env.company.id,
        })
        product = self.product_delivery_manual4.copy({'project_template_id': template.id})
        order = self._order(product)
        order.action_confirm()
        self.assertEqual(order.order_line.project_id.name, order.dvz_project_name)
        self.assertEqual(template.name, 'Example Actual Template')

    def test_missing_abbreviation_blocks_confirmation(self):
        self.env.user.dvz_sales_abbreviation = False
        order = self._order()
        with self.assertRaises(UserError):
            order.action_confirm()
        self.assertEqual(order.state, 'draft')
        self.assertFalse(order.order_line.project_id)

    def test_partial_naming_blocks_confirmation(self):
        order = self._order(dvz_project_reference=False)
        with self.assertRaises(UserError):
            order.action_confirm()
        self.assertEqual(order.state, 'draft')

    def test_archived_division_blocks_confirmation(self):
        order = self._order()
        self.division.active = False
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_no_naming_leaves_native_flow_alone(self):
        order = self._order(naming=False)
        order.action_confirm()
        self.assertTrue(order.order_line.project_id)
        self.assertFalse(order.order_line.project_id.dvz_project_code)
        self.assertFalse(order.dvz_confirmed_project_code)

    def test_naming_does_not_create_project_for_nonproject_product(self):
        before = self.env['project.project'].search_count([])
        order = self._order(self.product_delivery_manual1)
        order.action_confirm()
        self.assertFalse(order.order_line.project_id)
        self.assertEqual(self.env['project.project'].search_count([]), before)

    def test_shared_existing_project_not_renamed(self):
        old_name = self.project_global.name
        order = self._order(self.product_delivery_manual2)
        order.action_confirm()
        self.assertEqual(self.project_global.name, old_name)
        self.assertFalse(self.project_global.dvz_project_code)
        self.assertEqual(order.order_line.task_id.project_id, self.project_global)

    def test_cancel_draft_reconfirm_does_not_duplicate_project(self):
        order = self._order()
        order.action_confirm()
        project = order.order_line.project_id
        before = self.env['project.project'].search_count([])
        order._action_cancel()
        order.action_draft()
        order.action_confirm()
        self.assertEqual(order.order_line.project_id, project)
        self.assertEqual(self.env['project.project'].search_count([]), before)

    def test_confirmed_naming_snapshot_is_stable(self):
        order = self._order()
        order.action_confirm()
        project = order.order_line.project_id
        original = project.name
        self.env.user.dvz_sales_abbreviation = 'NEW'
        self.division.code = 'NEWEM'
        self.assertEqual(order.dvz_project_code, 'AIB-EM-4128-VO')
        self.assertEqual(project.name, original)
        with self.assertRaises(UserError):
            order.write({'dvz_project_reference': '9999'})

    def test_copy_requires_new_reference(self):
        order = self._order()
        order.action_confirm()
        copy = order.copy()
        self.assertFalse(copy.dvz_project_reference)
        self.assertFalse(copy.dvz_project_suffix)
        self.assertFalse(copy.dvz_confirmed_project_code)
        with self.assertRaises(UserError):
            copy.action_confirm()

    def test_direct_automation_with_native_order_link(self):
        order = self._order(self.product_delivery_manual1)
        order.action_confirm()
        project = self.env['project.project'].create({
            'name': 'Old automation default name',
            'company_id': order.company_id.id,
            'partner_id': order.partner_id.id,
            'reinvoiced_sale_order_id': order.id,
            'allow_billable': True,
        })
        self.assertEqual(project.name, order.dvz_project_name)
        self.assertEqual(project.dvz_origin_sale_id, order)

    def test_unlinked_project_not_renamed(self):
        order = self._order()
        project = self.env['project.project'].create({'name': order.name})
        self.assertEqual(project.name, order.name)
        self.assertFalse(project.dvz_origin_sale_id)

    def test_invalid_codes_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.division.write({'code': 'E M'})
        with self.assertRaises(ValidationError):
            self.env.user.write({'dvz_sales_abbreviation': 'A I B'})

    def test_division_company_cannot_change_while_used(self):
        self._order()
        other_company = self.env['res.company'].create({'name': 'Other Naming Company'})
        with self.assertRaises(UserError):
            self.division.write({'company_id': other_company.id})
