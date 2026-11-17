"""Odoo integration tests: run on a disposable Odoo 19 database only.

These tests are included for execution on the target server. They are NOT
claimed as executed by the isolated build-time test report.
"""
from unittest.mock import patch
from lxml import etree

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install", "dvz_sale_order_lock")
class TestSaleOrderLock(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.staff = new_test_user(
            cls.env, login="dvz_lock_staff",
            groups="sales_team.group_sale_salesman_all_leads",
        )
        cls.editor = new_test_user(
            cls.env, login="dvz_lock_editor",
            groups="sales_team.group_sale_salesman_all_leads,"
                   "dvz_sale_order_lock.group_manage_locked_sale_orders",
        )
        cls.sales_manager_without_lock = new_test_user(
            cls.env, login="dvz_lock_sales_manager",
            groups="sales_team.group_sale_manager",
        )
        cls.partner = cls.env["res.partner"].create({"name": "DVZ Lock Test Customer"})
        cls.product = cls.env["product.product"].create({
            "name": "DVZ Lock Test Service", "type": "service", "list_price": 100,
        })

    def _order(self, closed=False):
        order = self.env["sale.order"].with_user(self.staff).create({
            "partner_id": self.partner.id,
            "order_line": [fields.Command.create({
                "product_id": self.product.id, "product_uom_qty": 2,
                "price_unit": 100,
            })],
        })
        # Keep the test independent of the database's auto-lock setting.
        with patch.object(type(order), "_should_be_locked", return_value=False):
            order.action_confirm()
        if closed:
            order.with_user(self.editor).action_dvz_close()
        return order

    def test_status_open_closed_and_reopen(self):
        order = self._order()
        self.assertEqual(order.dvz_lock_status, "open")
        order.with_user(self.editor).action_dvz_close()
        self.assertEqual(order.dvz_lock_status, "closed")
        order.with_user(self.editor).action_dvz_open()
        self.assertEqual(order.dvz_lock_status, "open")
        self.assertEqual(order.state, "sale")

    def test_header_write_blocked_for_staff(self):
        order = self._order(closed=True)
        with self.assertRaises(AccessError):
            order.write({"client_order_ref": "Unauthorized"})

    def test_locked_line_write_blocked(self):
        order = self._order(closed=True)
        with self.assertRaises(AccessError):
            order.order_line.write({"price_unit": 1})
        with self.assertRaises(AccessError):
            order.order_line.write({"name": "Unauthorized description"})

    def test_locked_line_create_blocked(self):
        order = self._order(closed=True)
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].with_user(self.staff).create({
                "order_id": order.id, "display_type": "line_note", "name": "Unauthorized",
            })

    def test_default_order_id_does_not_bypass_guard(self):
        order = self._order(closed=True)
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].with_user(self.staff).with_context(
                default_order_id=order.id,
            ).create({"display_type": "line_note", "name": "Unauthorized"})

    def test_note_line_delete_blocked(self):
        order = self._order()
        note = self.env["sale.order.line"].with_user(self.staff).create({
            "order_id": order.id, "display_type": "line_note", "name": "Protected note",
        })
        order.with_user(self.editor).action_dvz_close()
        with self.assertRaises(AccessError):
            note.unlink()

    def test_move_line_out_of_closed_order_blocked(self):
        closed = self._order(closed=True)
        opened = self._order()
        with self.assertRaises(AccessError):
            closed.order_line.write({"order_id": opened.id})

    def test_move_line_into_closed_order_blocked(self):
        closed = self._order(closed=True)
        opened = self._order()
        with self.assertRaises(AccessError):
            opened.order_line.write({"order_id": closed.id})

    def test_group_cannot_edit_without_reopening(self):
        order = self._order(closed=True).with_user(self.editor)
        with self.assertRaises(AccessError):
            order.write({"client_order_ref": "Approved"})
        with self.assertRaises(AccessError):
            order.order_line.write({"price_unit": 125})
        self.assertEqual(order.order_line.price_unit, 100)
        self.assertTrue(order.locked)
        self.assertEqual(order.dvz_lock_status, "closed")

    def test_native_unlock_and_direct_write_require_group(self):
        order = self._order(closed=True)
        with self.assertRaises(AccessError):
            order.action_unlock()
        with self.assertRaises(AccessError):
            order.write({"locked": False})

    def test_sales_manager_does_not_implicitly_get_permission(self):
        order = self._order(closed=True).with_user(self.sales_manager_without_lock)
        with self.assertRaises(AccessError):
            order.action_unlock()
        with self.assertRaises(AccessError):
            order.write({"client_order_ref": "Not authorized"})

    def test_forced_context_flags_are_not_an_edit_bypass(self):
        order = self._order(closed=True).with_context(
            dvz_allow_locked_write=True, bypass_lock=True, sudo=True,
            _dvz_lock_confirmation=True, sale_write_from_compute=True,
        )
        with self.assertRaises(AccessError):
            order.write({"note": "Not permitted"})

    def test_status_cannot_be_imported_to_bypass_lock(self):
        order = self._order(closed=True)
        with self.assertRaises(AccessError):
            order.write({"dvz_lock_status": "open"})

    def test_automatic_lock_during_confirmation(self):
        order = self.env["sale.order"].with_user(self.staff).create({
            "partner_id": self.partner.id,
            "order_line": [fields.Command.create({
                "product_id": self.product.id, "product_uom_qty": 1, "price_unit": 100,
            })],
        })
        with patch.object(type(order), "_should_be_locked", return_value=True):
            order.action_confirm()
        self.assertTrue(order.locked)
        self.assertEqual(order.dvz_lock_status, "closed")

    def test_stored_status_search_and_grouping(self):
        opened = self._order()
        closed = self._order(closed=True)
        orders = self.env["sale.order"].with_user(self.staff)
        self.assertEqual(
            orders.search([("id", "in", (opened | closed).ids), ("dvz_lock_status", "=", "closed")]),
            closed,
        )
        groups = orders._read_group(
            [("id", "in", (opened | closed).ids)], ["dvz_lock_status"], ["__count"],
        )
        self.assertEqual(dict(groups), {"open": 1, "closed": 1})

    def test_mixed_batch_is_rejected(self):
        opened = self._order()
        closed = self._order(closed=True)
        with self.assertRaises(AccessError):
            (opened | closed).write({"client_order_ref": "Batch change"})

    def test_user_specific_readonly_flag(self):
        order = self._order(closed=True)
        self.assertTrue(order.with_user(self.staff).dvz_lock_readonly)
        self.assertTrue(order.with_user(self.editor).dvz_lock_readonly)
        self.assertFalse(order.with_user(self.staff).dvz_can_manage_lock)
        self.assertTrue(order.with_user(self.editor).dvz_can_manage_lock)

    def test_form_includes_generic_readonly_condition(self):
        result = self.env["sale.order"].with_user(self.staff).get_view(
            self.env.ref("sale.view_order_form").id, "form",
        )
        arch = etree.fromstring(result["arch"].encode())
        node = arch.xpath("//sheet//field[@name='client_order_ref']")[0]
        self.assertIn("dvz_lock_readonly", node.get("readonly", ""))
        self.assertTrue(arch.xpath("//field[@name='dvz_lock_readonly']"))

    def test_duplicate_creates_an_open_order(self):
        closed = self._order(closed=True)
        duplicate = closed.copy()
        self.assertFalse(duplicate.locked)
        self.assertEqual(duplicate.dvz_lock_status, "open")

    def test_form_uses_ribbons_not_header_badge(self):
        result = self.env["sale.order"].with_user(self.staff).get_view(
            self.env.ref("sale.view_order_form").id, "form",
        )
        arch = etree.fromstring(result["arch"].encode())
        header_status = arch.xpath("/form/header/field[@name='dvz_lock_status']")
        self.assertTrue(header_status)
        self.assertTrue(all(node.get("invisible") == "1" for node in header_status))
        self.assertFalse(arch.xpath("/form/header/field[@name='dvz_lock_status'][@widget='badge']"))
        closed = arch.xpath("/form/sheet/widget[@name='web_ribbon'][@title='Closed']")
        opened = arch.xpath("/form/sheet/widget[@name='web_ribbon'][@title='Open']")
        self.assertEqual(len(closed), 1)
        self.assertEqual(len(opened), 1)
        self.assertEqual(closed[0].get("invisible"), "not locked")
        self.assertEqual(opened[0].get("invisible"), "locked")

    def test_order_list_lock_status_follows_native_state(self):
        result = self.env["sale.order"].with_user(self.staff).get_view(
            self.env.ref("sale.view_order_tree").id, "list",
        )
        arch = etree.fromstring(result["arch"].encode())
        status = arch.xpath("/list/field[@name='dvz_lock_status']")
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0].getprevious().get("name"), "state")

    def test_quotation_list_lock_status_follows_native_state(self):
        result = self.env["sale.order"].with_user(self.staff).get_view(
            self.env.ref("sale.view_quotation_tree").id, "list",
        )
        arch = etree.fromstring(result["arch"].encode())
        status = arch.xpath("/list/field[@name='dvz_lock_status']")
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0].getprevious().get("name"), "state")

    def test_group_must_reopen_to_add_edit_remove_note(self):
        order = self._order(closed=True).with_user(self.editor)
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].with_user(self.editor).create({
                "order_id": order.id, "display_type": "line_note", "name": "Blocked",
            })
        order.action_dvz_open()
        note = self.env["sale.order.line"].with_user(self.editor).create({
            "order_id": order.id, "display_type": "line_note", "name": "Allowed",
        })
        order.order_line.filtered(lambda line: not line.display_type).write({"price_unit": 125})
        order.action_dvz_close()
        with self.assertRaises(AccessError):
            note.write({"name": "Blocked"})
        with self.assertRaises(AccessError):
            note.unlink()
        order.action_dvz_open()
        note.unlink()
        self.assertFalse(note.exists())

    def test_parent_line_commands_cannot_bypass_closed_order(self):
        order = self._order(closed=True).with_user(self.editor)
        commands = [
            fields.Command.create({"display_type": "line_note", "name": "Blocked"}),
            fields.Command.update(order.order_line.id, {"price_unit": 1}),
            fields.Command.delete(order.order_line.id),
            fields.Command.clear(),
        ]
        for command in commands:
            with self.subTest(command=command), self.assertRaises(AccessError):
                order.write({"order_line": [command]})
        self.assertEqual(order.order_line.price_unit, 100)

    def test_unlock_must_be_separate_from_edit(self):
        order = self._order(closed=True).with_user(self.editor)
        with self.assertRaises(AccessError):
            order.write({"locked": False, "order_line": [
                fields.Command.update(order.order_line.id, {"price_unit": 1}),
            ]})
        self.assertTrue(order.locked)
        self.assertEqual(order.order_line.price_unit, 100)

    def test_sudo_does_not_bypass_line_guard(self):
        order = self._order(closed=True).sudo()
        with self.assertRaises(AccessError):
            order.order_line.write({"price_unit": 1})
        with self.assertRaises(AccessError):
            order.order_line.unlink()
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].sudo().create({
                "order_id": order.id, "display_type": "line_note", "name": "Blocked",
            })

    def test_manager_readonly_flags_cover_order_and_lines(self):
        order = self._order(closed=True).with_user(self.editor)
        self.assertTrue(order.dvz_can_manage_lock)
        self.assertTrue(order.dvz_lock_readonly)
        self.assertTrue(order.order_line.dvz_lock_readonly)
        order.action_dvz_open()
        self.assertFalse(order.dvz_lock_readonly)
        self.assertFalse(order.order_line.dvz_lock_readonly)

    def test_manager_cannot_reparent_closed_line(self):
        closed = self._order(closed=True).with_user(self.editor)
        opened = self._order().with_user(self.editor)
        with self.assertRaises(AccessError):
            closed.order_line.write({"order_id": opened.id})
        with self.assertRaises(AccessError):
            opened.order_line.write({"order_id": closed.id})

    def test_native_line_protection_retained_for_manager(self):
        order = self._order(closed=True).with_user(self.editor)
        protected = order.order_line._get_protected_fields()
        self.assertIn("price_unit", protected)
        self.assertIn("product_uom_qty", protected)
        self.assertIn("product_id", protected)

    def test_manager_form_order_line_widget_has_readonly_guard(self):
        result = self.env["sale.order"].with_user(self.editor).get_view(
            self.env.ref("sale.view_order_form").id, "form",
        )
        arch = etree.fromstring(result["arch"].encode())
        node = arch.xpath("//page[@name='order_lines']/field[@name='order_line']")[0]
        self.assertIn("dvz_lock_readonly", node.get("readonly", ""))

    def test_portal_preview_token_does_not_require_reopening(self):
        order = self._order(closed=True).with_user(self.editor)
        token = order._portal_ensure_token()
        self.assertTrue(token)
        self.assertTrue(order.locked)
        with self.assertRaises(AccessError):
            order.write({"access_token": "manual replacement"})
