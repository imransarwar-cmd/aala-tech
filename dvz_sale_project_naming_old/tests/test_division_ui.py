"""Live Odoo tests for the 1.1.0 UI/mail changes; not standalone tests."""
from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestDivisionUI(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.division = cls.env['dvz.sale.division'].create({
            'name': 'Division UI Test', 'code': 'UITEST',
            'company_id': cls.env.company.id,
        })
        cls.reader = new_test_user(
            cls.env, login='dvz_division_reader_ui',
            groups='base.group_user,sales_team.group_sale_salesman',
            company_id=cls.env.company.id,
            company_ids=[Command.set(cls.env.company.ids)],
        )

    def test_chatter_and_activity_models_are_registered(self):
        for name in ('message_ids', 'message_follower_ids', 'activity_ids'):
            self.assertIn(name, self.division._fields)

    def test_internal_reader_can_log_note_without_changing_master(self):
        record = self.division.with_user(self.reader)
        note = record.with_context(mail_notify_force_send=False).message_post(
            body='Internal division review note', subtype_xmlid='mail.mt_note',
            message_type='comment',
        )
        self.assertEqual(note.model, 'dvz.sale.division')
        self.assertEqual(note.res_id, self.division.id)
        self.assertEqual(self.division.code, 'UITEST')

    def test_internal_reader_cannot_edit_master(self):
        with self.assertRaises(AccessError):
            self.division.with_user(self.reader).write({'code': 'EDITED'})

    def test_division_form_has_one_chatter(self):
        result = self.env['dvz.sale.division'].get_view(
            view_id=self.env.ref('dvz_sale_project_naming.division_view_form').id,
            view_type='form',
        )
        arch = etree.fromstring(result['arch'])
        self.assertEqual(len(arch.xpath('./chatter')), 1)
        self.assertFalse(arch.xpath('./sheet//chatter'))

    def test_both_division_menus_share_the_same_action(self):
        config = self.env.ref('dvz_sale_project_naming.menu_divisions')
        orders = self.env.ref('dvz_sale_project_naming.menu_divisions_orders')
        self.assertEqual(config.action, orders.action)
        self.assertEqual(orders.parent_id, self.env.ref('sale.sale_order_menu'))

    def test_sale_form_has_project_information_and_one_division(self):
        result = self.env['sale.order'].get_view(
            view_id=self.env.ref('sale.view_order_form').id, view_type='form',
        )
        arch = etree.fromstring(result['arch'])
        group = arch.xpath("./sheet/group[@name='dvz_project_information']")
        self.assertEqual(len(group), 1)
        self.assertEqual(len(group[0].xpath('.//field[@name="dvz_division_id"]')), 1)
        self.assertFalse(arch.xpath(".//page[@name='other_information']//field[@name='dvz_division_id']"))
        self.assertEqual(len(arch.xpath('./chatter')), 1)

    def test_sale_search_has_division_group_by(self):
        result = self.env['sale.order'].get_view(
            view_id=self.env.ref('sale.view_sales_order_filter').id, view_type='search',
        )
        arch = etree.fromstring(result['arch'])
        self.assertEqual(len(arch.xpath('.//filter[@name="dvz_group_by_division"]')), 1)

    def test_manager_can_schedule_division_activity(self):
        activity = self.division.activity_schedule(
            'mail.mail_activity_data_todo', summary='Review division configuration',
            user_id=self.env.user.id,
        )
        self.assertEqual(activity.res_model, 'dvz.sale.division')
        self.assertEqual(activity.res_id, self.division.id)
        self.assertIn(activity, self.division.activity_ids)

    def test_key_division_fields_have_tracking_enabled(self):
        for name in ('name', 'code', 'company_id', 'active'):
            self.assertTrue(self.division._fields[name].tracking)
