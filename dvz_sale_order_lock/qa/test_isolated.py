"""Run without Odoo: pure helpers plus actual addon guard methods on ORM doubles.
These checks are not a database, registry, HTTP, or browser integration test.
"""
import ast
import copy
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Package shells avoid importing the Odoo __init__ before installing test doubles.
for name in ["dvz_lock_test", "dvz_lock_test.models"]:
    mod = types.ModuleType(name)
    mod.__path__ = [str(ROOT if name == "dvz_lock_test" else ROOT / "models")]
    sys.modules[name] = mod
policy = load("dvz_lock_test.models.policy", ROOT / "models/policy.py")
view_utils = load("dvz_lock_test.models.view_utils", ROOT / "models/view_utils.py")


class TestPolicy(unittest.TestCase):
    def test_open_status(self):
        self.assertEqual(policy.lock_status(False), "open")

    def test_closed_status(self):
        self.assertEqual(policy.lock_status(True), "closed")

    def test_no_scope_by_default(self):
        self.assertFalse(policy.in_server_scope("confirm", object(), [1]))

    def test_scope_permits_exact_ids_and_subset(self):
        cr = object()
        with policy.server_scope("confirm", cr, [1, 2]):
            self.assertTrue(policy.in_server_scope("confirm", cr, [1, 2]))
            self.assertTrue(policy.in_server_scope("confirm", cr, [2]))

    def test_scope_does_not_permit_other_records(self):
        cr = object()
        with policy.server_scope("confirm", cr, [1]):
            self.assertFalse(policy.in_server_scope("confirm", cr, [1, 2]))
            self.assertFalse(policy.in_server_scope("confirm", cr, []))

    def test_scope_does_not_cross_transactions(self):
        with policy.server_scope("confirm", object(), [1]):
            self.assertFalse(policy.in_server_scope("confirm", object(), [1]))

    def test_scope_not_a_general_write_permission(self):
        cr = object()
        with policy.server_scope("confirm", cr, [1]):
            self.assertTrue(policy.is_confirmation_lock({"locked": True}, cr, [1]))
            self.assertFalse(policy.is_confirmation_lock({"locked": False}, cr, [1]))
            self.assertFalse(policy.is_confirmation_lock({"locked": True, "note": "hack"}, cr, [1]))

    def test_scope_cleanup_on_exception(self):
        cr = object()
        with self.assertRaises(ValueError):
            with policy.server_scope("confirm", cr, [1]):
                raise ValueError("test")
        self.assertFalse(policy.in_server_scope("confirm", cr, [1]))

    def test_nested_scope_restored(self):
        cr = object()
        with policy.server_scope("confirm", cr, [1]):
            with policy.server_scope("confirmation_mail", cr, [2]):
                self.assertTrue(policy.in_server_scope("confirmation_mail", cr, [2]))
            self.assertFalse(policy.in_server_scope("confirmation_mail", cr, [2]))
            self.assertTrue(policy.in_server_scope("confirm", cr, [1]))

    def test_mail_scope_only_allows_metadata(self):
        cr = object()
        with policy.server_scope("confirmation_mail", cr, [1]):
            self.assertTrue(policy.is_mail_metadata_write({"pending_email_template_id": 1}, cr, [1]))
            self.assertFalse(policy.is_mail_metadata_write({"note": "hack"}, cr, [1]))
            self.assertFalse(policy.is_mail_metadata_write({"pending_email_template_id": 1, "note": "hack"}, cr, [1]))


RELATIONS = {
    ("sale.order", "order_line"): "sale.order.line",
    ("sale.order", "x_detail_ids"): "x.detail",
    ("sale.order.line", "product_custom_attribute_value_ids"): "product.attribute.custom.value",
    ("sale.order", "x_dvz_department_ids"): "division.master",
}


class TestView(unittest.TestCase):
    def process(self, xml, model="sale.order"):
        arch = etree.fromstring(xml.encode())
        return view_utils.protect_view(arch, model, lambda m, f: RELATIONS.get((m, f)))

    def test_plain_and_custom_fields_readonly(self):
        arch = self.process('<form><sheet><field name="note"/><field name="x_comment"/><field name="x_dvz_department_ids" widget="many2many_tags"/></sheet></form>')
        for name in ["note", "x_comment", "x_dvz_department_ids"]:
            self.assertEqual(arch.xpath(f"//field[@name='{name}']")[0].get("readonly"), "dvz_lock_readonly")

    def test_existing_business_readonly_preserved(self):
        arch = self.process('''<form><field name="partner_id" readonly="state in ['cancel','sale']"/></form>''')
        self.assertIn("state in", arch.xpath("//field[@name='partner_id']")[0].get("readonly"))

    def test_native_locked_condition_replaced(self):
        arch = self.process('''<form><field name="order_line" readonly="state == 'cancel' or locked"/></form>''')
        expr = arch.xpath("//field[@name='order_line']")[0].get("readonly")
        self.assertFalse(eval(expr, {}, {"state": "sale", "dvz_lock_readonly": False}))
        self.assertTrue(eval(expr, {}, {"state": "sale", "dvz_lock_readonly": True}))
        self.assertTrue(eval(expr, {}, {"state": "cancel", "dvz_lock_readonly": False}))

    def test_nested_sale_line_custom_fields_protected(self):
        arch = self.process('<form><field name="order_line"><list><field name="price_unit"/><field name="x_notes"/></list><form><field name="name"/></form></field></form>')
        for name in ["price_unit", "x_notes", "name"]:
            self.assertEqual(arch.xpath(f"//field[@name='{name}']")[0].get("readonly"), "dvz_lock_readonly")
        self.assertEqual(len(arch.xpath("//field[@name='dvz_lock_readonly']")), 3)

    def test_unrelated_child_locked_not_rewritten(self):
        arch = self.process('<form><field name="x_detail_ids"><list><field name="locked"/><field name="name" readonly="locked"/></list></field></form>')
        self.assertEqual(arch.xpath("//list/field[@name='name']")[0].get("readonly"), "locked")
        self.assertEqual(arch.xpath("//field[@name='x_detail_ids']")[0].get("readonly"), "dvz_lock_readonly")

    def test_parent_locked_on_sale_line_rewritten(self):
        arch = self.process('<form><field name="order_line"><list><field name="name" readonly="parent.locked"/></list></field></form>')
        self.assertIn("parent.dvz_lock_readonly", arch.xpath("//list/field[@name='name']")[0].get("readonly"))

    def test_locked_word_in_string_literal_untouched(self):
        expr = "state == 'locked' or locked"
        result = view_utils.replace_lock_condition(expr, "sale.order")
        self.assertEqual(result, "state == 'locked' or dvz_lock_readonly")

    def test_always_readonly_stays_readonly(self):
        arch = self.process('<form><field name="amount_total" readonly="1"/></form>')
        self.assertEqual(arch.xpath("//field[@name='amount_total']")[0].get("readonly"), "1")

    def test_helpers_hidden_in_list(self):
        arch = self.process('<list><field name="name"/></list>')
        helper = arch.xpath("//field[@name='dvz_lock_readonly']")[0]
        self.assertEqual(helper.get("column_invisible"), "1")
        self.assertEqual(helper.get("readonly"), "1")

    def test_helpers_not_groups_restricted(self):
        arch = self.process('<form><field name="dvz_lock_readonly" groups="base.group_no_one"/></form>')
        self.assertEqual(len(arch.xpath("//field[@name='dvz_lock_readonly' and not(@groups)]")), 1)

    def test_original_lock_buttons_hidden(self):
        arch = self.process('<form><header><button name="action_lock"/><button name="action_unlock"/><button name="action_dvz_open"/></header></form>')
        self.assertEqual(arch.xpath("//button[@name='action_lock']")[0].get("invisible"), "1")
        self.assertEqual(arch.xpath("//button[@name='action_unlock']")[0].get("invisible"), "1")
        self.assertIsNone(arch.xpath("//button[@name='action_dvz_open']")[0].get("invisible"))

    def test_business_actions_hidden_but_read_actions_kept(self):
        arch = self.process('<form><header><button name="action_update_prices"/><button name="action_view_invoice"/></header></form>')
        self.assertEqual(arch.xpath("//button[@name='action_update_prices']")[0].get("invisible"), "dvz_lock_readonly")
        self.assertIsNone(arch.xpath("//button[@name='action_view_invoice']")[0].get("invisible"))

    def test_transformation_idempotent(self):
        arch = self.process('<form><field name="order_line" readonly="locked"><list><field name="price_unit"/></list></field><field name="note"/></form>')
        first = etree.tostring(arch)
        view_utils.protect_view(arch, "sale.order", lambda m, f: RELATIONS.get((m, f)))
        self.assertEqual(first, etree.tostring(arch))

    def test_standalone_line_view_readonly(self):
        arch = self.process('<form><field name="order_id"/><field name="name"/><field name="x_custom"/></form>', "sale.order.line")
        self.assertEqual(arch.xpath("//field[@name='x_custom']")[0].get("readonly"), "dvz_lock_readonly")


class AccessError(Exception):
    pass


class UserError(Exception):
    pass


class DummyAPI:
    model = staticmethod(lambda method: method)
    model_create_multi = staticmethod(lambda method: method)
    depends = staticmethod(lambda *a: (lambda method: method))
    depends_context = staticmethod(lambda *a: (lambda method: method))


class FakeField:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.comodel_name = kwargs.get("comodel_name")
        self.name = None

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        return obj._one().get(self.name, False)

    def __set__(self, obj, value):
        for rid in obj.ids:
            obj.env.data[obj._name][rid][self.name] = value


class Cursor:
    def __init__(self, env):
        self.env = env
        self.queries = []
        self.rows = []

    def execute(self, query, params):
        self.queries.append((query, params))
        self.rows = [(rid, self.env.data["sale.order"][rid].get("locked", False))
                     for rid in params[0] if rid in self.env.data["sale.order"]]

    def fetchall(self):
        return self.rows


class CoreModel:
    def __init__(self, env, ids=()):
        self.env = env
        self.ids = list(ids)
        self._name = self._inherit

    def _one(self):
        return self.env.data[self._name][self.ids[0]] if self.ids else {}

    def __getattr__(self, name):
        if name == "order_id":
            ids = [self.env.data[self._name][i].get("order_id") for i in self.ids]
            return self.env["sale.order"].browse(list(dict.fromkeys(i for i in ids if i)))
        if name == "sale_order_line_id":
            ids = [self.env.data[self._name][i].get("sale_order_line_id") for i in self.ids]
            return self.env["sale.order.line"].browse(list(dict.fromkeys(i for i in ids if i)))
        if name == "id":
            return self.ids[0] if self.ids else False
        return self._one().get(name, False)

    def __bool__(self):
        return bool(self.ids)

    def __iter__(self):
        return (self.browse([i]) for i in self.ids)

    def __or__(self, other):
        assert other._name == self._name
        return self.browse(list(dict.fromkeys(self.ids + other.ids)))

    def browse(self, ids=()):
        return type(self)(self.env, [ids] if isinstance(ids, int) else ids)

    def check_access(self, operation):
        if operation in self.env.denied:
            raise AccessError("Normal ACL/record rule denied")

    def flush_recordset(self, names):
        pass

    def invalidate_recordset(self, names, flush=True):
        pass

    def default_get(self, names):
        return {name: self.env.context.get("default_" + name, False) for name in names}

    def write(self, vals):
        self.check_access("write")
        for rid in self.ids:
            self.env.data[self._name][rid].update(vals)
        return True

    def create(self, vals_list):
        self.check_access("create")
        ids = []
        for vals in vals_list:
            default = {k[8:]: v for k, v in self.env.context.items() if k.startswith("default_")}
            values = dict(default, **vals)
            if self._name == "sale.order":
                values.setdefault("locked", False)
                values.setdefault("state", "draft")
            rid = max(self.env.data[self._name], default=0) + 1
            self.env.data[self._name][rid] = values
            ids.append(rid)
        return self.browse(ids)

    def unlink(self):
        self.check_access("unlink")
        for rid in self.ids:
            del self.env.data[self._name][rid]
        return True

    def action_lock(self):
        return self.write({"locked": True})

    def action_unlock(self):
        return self.write({"locked": False})

    def action_confirm(self):
        self.write({"state": "sale"})
        if self.env.auto_lock:
            self.action_lock()
        return True

    def _send_order_notification_mail(self, *args, **kwargs):
        return self.write({"pending_email_template_id": 1})

    def _cron_send_pending_emails(self):
        return self.env["sale.order"].browse(1).write({"pending_email_template_id": False})

    def _portal_ensure_token(self):
        if not self.access_token:
            self.write({"access_token": "TEST_ONLY_TOKEN"})
        return self.access_token

    def action_update_prices(self):
        return "prices"

    def action_update_taxes(self):
        return "taxes"

    def action_open_discount_wizard(self):
        return {"res_model": "sale.order.discount"}

    def _get_protected_fields(self):
        return ["price_unit", "name"]

    def _get_view(self, *args, **kwargs):
        return etree.fromstring(b'<form><field name="note"/></form>'), None


odoo = types.ModuleType("odoo")
odoo.api = DummyAPI
odoo.models = types.SimpleNamespace(Model=CoreModel)
odoo.fields = types.SimpleNamespace(Boolean=FakeField, Selection=FakeField)
odoo._ = lambda message, *args, **kwargs: message
sys.modules["odoo"] = odoo
exceptions = types.ModuleType("odoo.exceptions")
exceptions.AccessError, exceptions.UserError = AccessError, UserError
sys.modules["odoo.exceptions"] = exceptions
so = load("dvz_lock_test.models.sale_order", ROOT / "models/sale_order.py")
sol = load("dvz_lock_test.models.sale_order_line", ROOT / "models/sale_order_line.py")
pacv = load("dvz_lock_test.models.product_attribute_custom_value", ROOT / "models/product_attribute_custom_value.py")


class Env:
    def __init__(self, allowed=False, su=False):
        self.su = su
        self.allowed = allowed
        self.user = types.SimpleNamespace(has_group=lambda name: self.allowed and name == policy.LOCK_GROUP)
        self.context = {}
        self.data = {
            "sale.order": {1: {"locked": True, "state": "sale"}, 2: {"locked": False, "state": "sale"}},
            "sale.order.line": {10: {"order_id": 1, "price_unit": 100}, 20: {"order_id": 2, "price_unit": 100}},
            "product.attribute.custom.value": {100: {"sale_order_line_id": 10, "custom_value": "A"}},
        }
        self.denied = set()
        self.cr = Cursor(self)
        self.auto_lock = False

    def __getitem__(self, key):
        cls = {"sale.order": so.SaleOrder, "sale.order.line": sol.SaleOrderLine,
               "product.attribute.custom.value": pacv.ProductAttributeCustomValue}[key]
        return cls(self)


class TestActualGuardMethods(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.closed = self.env["sale.order"].browse(1)
        self.opened = self.env["sale.order"].browse(2)
        self.closed_line = self.env["sale.order.line"].browse(10)
        self.open_line = self.env["sale.order.line"].browse(20)

    def test_closed_header_edit_denied(self):
        with self.assertRaises(AccessError):
            self.closed.write({"client_order_ref": "no"})

    def test_closed_custom_field_edit_denied(self):
        with self.assertRaises(AccessError):
            self.closed.write({"x_studio_custom_field": "no"})

    def test_closed_many2many_edit_denied(self):
        with self.assertRaises(AccessError):
            self.closed.write({"dvz_department_ids": [(6, 0, [1, 2])]})

    def test_open_edit_allowed(self):
        self.opened.write({"x_notes": "yes"})
        self.assertEqual(self.opened.x_notes, "yes")

    def test_group_cannot_edit_closed_header(self):
        self.env.allowed = True
        with self.assertRaises(AccessError):
            self.closed.write({"x_notes": "approved"})
        self.assertFalse(self.closed.x_notes)
        self.assertTrue(self.closed.locked)

    def test_sudo_does_not_bypass_closed_business_edit(self):
        self.env.su = True
        with self.assertRaises(AccessError):
            self.closed.write({"note": "server"})
        self.assertFalse(self.closed.note)

    def test_group_does_not_bypass_existing_acl(self):
        self.env.allowed = True
        self.env.denied.add("write")
        with self.assertRaisesRegex(AccessError, "Normal ACL"):
            self.closed.write({"note": "no"})

    def test_mixed_batch_rejected_before_mutation(self):
        with self.assertRaises(AccessError):
            (self.closed | self.opened).write({"note": "no"})
        self.assertFalse(self.opened.note)

    def test_unlock_and_edit_in_same_write_denied(self):
        with self.assertRaises(AccessError):
            self.closed.write({"locked": False, "note": "no"})
        self.assertTrue(self.closed.locked)

    def test_explicit_lock_requires_group(self):
        with self.assertRaises(AccessError):
            self.opened.action_lock()

    def test_native_unlock_requires_group(self):
        with self.assertRaises(AccessError):
            self.closed.action_unlock()

    def test_group_native_lock_unlock(self):
        self.env.allowed = True
        self.opened.action_lock()
        self.assertTrue(self.opened.locked)
        self.opened.action_unlock()
        self.assertFalse(self.opened.locked)

    def test_close_only_confirmed_orders(self):
        self.env.allowed = True
        self.env.data["sale.order"][2]["state"] = "draft"
        with self.assertRaises(UserError):
            self.opened.action_dvz_close()

    def test_group_close_reopen_buttons(self):
        self.env.allowed = True
        self.opened.action_dvz_close()
        self.assertTrue(self.opened.locked)
        self.opened.action_dvz_open()
        self.assertFalse(self.opened.locked)
        self.assertEqual(self.opened.state, "sale")

    def test_status_field_cannot_be_forged(self):
        with self.assertRaises(AccessError):
            self.opened.write({"dvz_lock_status": "closed"})

    def test_permissions_cannot_be_forged(self):
        with self.assertRaises(AccessError):
            self.closed.write({"dvz_can_manage_lock": True})

    def test_context_bypass_flags_ignored(self):
        self.env.context.update(sudo=True, bypass_lock=True, dvz_allow_locked_write=True)
        with self.assertRaises(AccessError):
            self.closed.write({"note": "no"})

    def test_native_automatic_confirmation_lock(self):
        self.env.auto_lock = True
        self.env.data["sale.order"][2]["state"] = "draft"
        self.opened.action_confirm()
        self.assertTrue(self.opened.locked)
        with self.assertRaises(AccessError):
            self.opened.write({"note": "not allowed after confirmation"})

    def test_confirming_closed_order_denied(self):
        with self.assertRaises(AccessError):
            self.closed.action_confirm()

    def test_native_protected_fields_preserved_for_group(self):
        self.assertEqual(self.closed_line._get_protected_fields(), ["price_unit", "name"])
        self.env.allowed = True
        self.assertEqual(self.closed_line._get_protected_fields(), ["price_unit", "name"])

    def test_line_write_blocked(self):
        with self.assertRaises(AccessError):
            self.closed_line.write({"price_unit": 1})

    def test_line_custom_write_blocked(self):
        with self.assertRaises(AccessError):
            self.closed_line.write({"x_custom": "no"})

    def test_line_reparent_from_closed_denied(self):
        with self.assertRaises(AccessError):
            self.closed_line.write({"order_id": 2})

    def test_line_reparent_to_closed_denied(self):
        with self.assertRaises(AccessError):
            self.open_line.write({"order_id": 1})

    def test_group_line_edit_denied_while_closed(self):
        self.env.allowed = True
        with self.assertRaises(AccessError):
            self.closed_line.write({"price_unit": 125})
        self.assertEqual(self.closed_line.price_unit, 100)

    def test_closed_line_create_denied(self):
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].create([{"order_id": 1, "name": "no"}])

    def test_default_closed_order_line_create_denied(self):
        self.env.context["default_order_id"] = 1
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].create([{"name": "no"}])

    def test_open_line_create_allowed(self):
        line = self.env["sale.order.line"].create([{"order_id": 2, "name": "yes"}])
        self.assertEqual(line.name, "yes")

    def test_group_closed_line_create_denied(self):
        self.env.allowed = True
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].create([{"order_id": 1, "name": "yes"}])
        self.assertEqual(len(self.env.data["sale.order.line"]), 2)

    def test_line_delete_denied(self):
        with self.assertRaises(AccessError):
            self.closed_line.unlink()

    def test_order_delete_denied(self):
        with self.assertRaises(AccessError):
            self.closed.unlink()

    def test_creation_with_locked_flag_denied(self):
        with self.assertRaises(AccessError):
            self.env["sale.order"].create([{"locked": True}])

    def test_creation_with_default_locked_flag_denied(self):
        self.env.context["default_locked"] = True
        with self.assertRaises(AccessError):
            self.env["sale.order"].create([{"name": "no"}])

    def test_creation_open_allowed(self):
        order = self.env["sale.order"].create([{"name": "yes"}])
        self.assertFalse(order.locked)

    def test_mail_metadata_can_only_be_written_in_private_scope(self):
        with self.assertRaises(AccessError):
            self.closed.write({"pending_email_template_id": 1})
        self.closed._send_order_notification_mail(None)
        self.assertEqual(self.closed.pending_email_template_id, 1)
        with self.assertRaises(AccessError):
            self.closed.write({"note": "no"})

    def test_price_action_denied(self):
        with self.assertRaises(AccessError):
            self.closed.action_update_prices()

    def test_tax_action_denied(self):
        with self.assertRaises(AccessError):
            self.closed.action_update_taxes()

    def test_discount_wizard_denied(self):
        with self.assertRaises(AccessError):
            self.closed.action_open_discount_wizard()

    def test_helpers_compute_per_user(self):
        self.closed._compute_dvz_lock_permissions()
        self.assertTrue(self.closed.dvz_lock_readonly)
        self.assertFalse(self.closed.dvz_can_manage_lock)
        self.env.allowed = True
        self.closed._compute_dvz_lock_permissions()
        self.assertTrue(self.closed.dvz_lock_readonly)
        self.assertTrue(self.closed.dvz_can_manage_lock)

    def test_line_helpers_compute_per_user(self):
        self.closed_line._compute_dvz_lock_permissions()
        self.assertTrue(self.closed_line.dvz_lock_readonly)
        self.env.allowed = True
        self.closed_line._compute_dvz_lock_permissions()
        self.assertTrue(self.closed_line.dvz_lock_readonly)

    def test_status_compute(self):
        (self.closed | self.opened)._compute_dvz_lock_status()
        self.assertEqual(self.closed.dvz_lock_status, "closed")
        self.assertEqual(self.opened.dvz_lock_status, "open")

    def test_parameterized_row_lock_used(self):
        self.opened.write({"note": "yes"})
        query, params = self.env.cr.queries[-1]
        self.assertIn("ORDER BY id FOR UPDATE", query)
        self.assertEqual(params, [(2,)])

    def test_custom_product_attribute_edit_denied(self):
        with self.assertRaises(AccessError):
            self.env["product.attribute.custom.value"].browse(100).write({"custom_value": "no"})

    def test_custom_product_attribute_reparent_denied(self):
        with self.assertRaises(AccessError):
            self.env["product.attribute.custom.value"].browse(100).write({"sale_order_line_id": 20})

    def test_custom_product_attribute_delete_denied(self):
        with self.assertRaises(AccessError):
            self.env["product.attribute.custom.value"].browse(100).unlink()

    def test_custom_product_attribute_create_denied(self):
        with self.assertRaises(AccessError):
            self.env["product.attribute.custom.value"].create([{"sale_order_line_id": 10, "custom_value": "no"}])


    def test_manager_cannot_combine_unlock_and_header_edit(self):
        self.env.allowed = True
        with self.assertRaises(AccessError):
            self.closed.write({"locked": False, "client_order_ref": "bypass"})
        self.assertTrue(self.closed.locked)

    def test_manager_cannot_combine_unlock_and_line_creation(self):
        self.env.allowed = True
        with self.assertRaises(AccessError):
            self.closed.write({"locked": False, "order_line": [(0, 0, {"name": "bypass"})]})
        self.assertTrue(self.closed.locked)

    def test_manager_must_reopen_before_header_and_line_edits(self):
        self.env.allowed = True
        self.closed.action_dvz_open()
        self.closed.write({"client_order_ref": "allowed after reopen"})
        self.closed_line.write({"price_unit": 140})
        self.assertEqual(self.closed_line.price_unit, 140)
        self.closed.action_dvz_close()
        with self.assertRaises(AccessError):
            self.closed_line.write({"price_unit": 145})

    def test_staff_can_edit_only_after_manager_reopens(self):
        self.env.allowed = True
        self.closed.action_dvz_open()
        self.env.allowed = False
        self.closed_line.write({"price_unit": 110})
        self.assertEqual(self.closed_line.price_unit, 110)

    def test_manager_line_delete_denied(self):
        self.env.allowed = True
        with self.assertRaises(AccessError):
            self.closed_line.unlink()
        self.assertIn(10, self.env.data["sale.order.line"])

    def test_manager_order_delete_denied(self):
        self.env.allowed = True
        with self.assertRaises(AccessError):
            self.closed.unlink()
        self.assertIn(1, self.env.data["sale.order"])

    def test_manager_line_moves_in_and_out_denied(self):
        self.env.allowed = True
        with self.assertRaises(AccessError):
            self.closed_line.write({"order_id": 2})
        with self.assertRaises(AccessError):
            self.open_line.write({"order_id": 1})

    def test_manager_reordering_and_custom_fields_denied(self):
        self.env.allowed = True
        for vals in [{"sequence": 2}, {"x_custom_field": "changed"},
                     {"tax_ids": [(5, 0, 0)]}, {"product_uom_qty": 999},
                     {"discount": 99}, {"name": "changed"}]:
            with self.subTest(values=vals), self.assertRaises(AccessError):
                self.closed_line.write(vals)

    def test_manager_parent_x2many_commands_denied(self):
        self.env.allowed = True
        # Actual ORM command execution is not mocked: rejection is required
        # before super.write sees any command, regardless of command code.
        commands = [
            (0, 0, {"name": "new"}), (1, 10, {"name": "edited"}),
            (2, 10, 0), (3, 10, 0), (4, 20, 0), (5, 0, 0), (6, 0, [20]),
        ]
        for cmd in commands:
            with self.subTest(command=cmd), self.assertRaises(AccessError):
                self.closed.write({"order_line": [cmd]})
        self.assertEqual(self.closed_line.price_unit, 100)
        self.assertIn(10, self.env.data["sale.order.line"])

    def test_manager_default_parent_create_denied(self):
        self.env.allowed = True
        self.env.context["default_order_id"] = 1
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].create([{"name": "default bypass"}])

    def test_manager_mixed_line_create_batch_is_atomic(self):
        self.env.allowed = True
        before = copy.deepcopy(self.env.data["sale.order.line"])
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].create([
                {"order_id": 2, "name": "open"},
                {"order_id": 1, "name": "closed"},
            ])
        self.assertEqual(before, self.env.data["sale.order.line"])

    def test_manager_mixed_line_write_batch_is_atomic(self):
        self.env.allowed = True
        with self.assertRaises(AccessError):
            (self.open_line | self.closed_line).write({"price_unit": 1})
        self.assertEqual(self.open_line.price_unit, 100)

    def test_sudo_cannot_create_edit_delete_closed_lines(self):
        self.env.su = True
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].create([{"order_id": 1, "name": "sudo"}])
        with self.assertRaises(AccessError):
            self.closed_line.write({"price_unit": 0})
        with self.assertRaises(AccessError):
            self.closed_line.unlink()

    def test_sudo_ui_flag_is_readonly(self):
        self.env.su = True
        self.closed._compute_dvz_lock_permissions()
        self.closed_line._compute_dvz_lock_permissions()
        self.assertTrue(self.closed.dvz_lock_readonly)
        self.assertTrue(self.closed_line.dvz_lock_readonly)
        self.assertTrue(self.closed.dvz_can_manage_lock)

    def test_manager_cannot_modify_custom_product_attribute(self):
        self.env.allowed = True
        attr = self.env["product.attribute.custom.value"].browse(100)
        with self.assertRaises(AccessError):
            attr.write({"custom_value": "new"})
        with self.assertRaises(AccessError):
            attr.unlink()

    def test_readonly_flags_follow_reopen_and_reclose(self):
        self.env.allowed = True
        self.closed.action_dvz_open()
        self.closed._compute_dvz_lock_permissions()
        self.closed_line._compute_dvz_lock_permissions()
        self.assertFalse(self.closed.dvz_lock_readonly)
        self.assertFalse(self.closed_line.dvz_lock_readonly)
        self.closed.action_dvz_close()
        self.closed._compute_dvz_lock_permissions()
        self.closed_line._compute_dvz_lock_permissions()
        self.assertTrue(self.closed.dvz_lock_readonly)
        self.assertTrue(self.closed_line.dvz_lock_readonly)

    def test_manager_mutation_actions_require_reopen(self):
        self.env.allowed = True
        for method in ("action_update_prices", "action_update_taxes", "action_open_discount_wizard"):
            with self.subTest(method=method), self.assertRaises(AccessError):
                getattr(self.closed, method)()

    def test_context_flags_never_bypass_manager_lock(self):
        self.env.allowed = True
        self.env.context.update(skip_dvz_lock=True, sudo=True, dvz_lock_readonly=False)
        with self.assertRaises(AccessError):
            self.closed_line.write({"name": "bypass"})

    def test_portal_token_scope_is_not_a_business_write_bypass(self):
        with policy.server_scope("portal_token", self.env.cr, [1]):
            with self.assertRaises(AccessError):
                self.closed.write({"access_token": "test", "note": "bypass"})
            with self.assertRaises(AccessError):
                self.closed_line.write({"price_unit": 0})

    def test_native_portal_helper_may_create_token_while_closed(self):
        self.assertEqual(self.closed._portal_ensure_token(), "TEST_ONLY_TOKEN")
        self.assertTrue(self.closed.locked)
        with self.assertRaises(AccessError):
            self.closed.write({"access_token": "manual reset"})

    def test_mail_cron_cleanup_scope_does_not_allow_business_edit(self):
        with policy.confirmation_mail_cron_scope(self.env.cr):
            self.closed.write({"pending_email_template_id": False})
            with self.assertRaises(AccessError):
                self.closed.write({"pending_email_template_id": False, "note": "bypass"})
        with self.assertRaises(AccessError):
            self.closed.write({"pending_email_template_id": False})

    def test_native_mail_cron_can_clear_metadata_only(self):
        self.env["sale.order"]._cron_send_pending_emails()
        self.assertFalse(self.closed.pending_email_template_id)
        self.assertTrue(self.closed.locked)

    def test_mail_cron_scope_does_not_cross_cursor_and_cleans_up(self):
        with policy.confirmation_mail_cron_scope(object()):
            with self.assertRaises(AccessError):
                self.closed.write({"pending_email_template_id": False})
        with self.assertRaises(ValueError):
            with policy.confirmation_mail_cron_scope(self.env.cr):
                raise ValueError("cleanup")
        with self.assertRaises(AccessError):
            self.closed.write({"pending_email_template_id": False})

class TestPackage(unittest.TestCase):
    def test_manifest_files_exist(self):
        manifest = ast.literal_eval((ROOT / "__manifest__.py").read_text())
        self.assertTrue(manifest["version"].startswith("19.0."))
        self.assertEqual(manifest["depends"], ["sale_management"])
        for file in manifest["data"]:
            self.assertTrue((ROOT / file).is_file(), file)

    def test_xml_parses(self):
        for path in ROOT.rglob("*.xml"):
            etree.parse(str(path))

    def test_python_parses(self):
        for path in ROOT.rglob("*.py"):
            ast.parse(path.read_text(), filename=str(path))

    def test_group_is_explicit_not_auto_granted(self):
        doc = etree.parse(str(ROOT / "security/sale_lock_groups.xml"))
        self.assertTrue(doc.xpath("//record[@model='res.groups.privilege']"))
        self.assertFalse(doc.xpath("//field[@name='user_ids']"))
        groups = doc.xpath("//record[@model='res.groups']")
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].get("id"), "group_manage_locked_sale_orders")

    def test_status_search_and_group_controls(self):
        doc = etree.parse(str(ROOT / "views/sale_order_views.xml"))
        self.assertEqual(len(doc.xpath("//filter[@name='dvz_open_orders']")), 1)
        self.assertEqual(len(doc.xpath("//filter[@name='dvz_closed_orders']")), 1)
        context = doc.xpath("//filter[@name='dvz_group_lock_status']")[0].get("context")
        self.assertEqual(ast.literal_eval(context), {"group_by": "dvz_lock_status"})

    def test_banner_fields_declared_for_view_validation(self):
        doc = etree.parse(str(ROOT / "views/sale_order_views.xml"))
        arch = doc.xpath("//record[@id='view_order_form_lock_control']/field[@name='arch']")[0]
        self.assertTrue(arch.xpath(".//field[@name='dvz_lock_readonly']"))
        self.assertTrue(arch.xpath(".//field[@name='locked']"))

    def test_no_javascript_or_original_addon_replacement(self):
        self.assertFalse(list(ROOT.rglob("*.js")))
        manifest = ast.literal_eval((ROOT / "__manifest__.py").read_text())
        self.assertNotIn("assets", manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
