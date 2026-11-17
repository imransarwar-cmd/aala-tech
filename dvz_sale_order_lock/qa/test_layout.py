"""Isolated XML layout tests; these do not run Odoo's registry or renderer.

The small fixtures reproduce the relevant Odoo 19 view anchors, not the entire
upstream form. The mini-applier covers only the XPath operations used here.
"""
import ast
import copy
from pathlib import Path
import unittest
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]

FORM = '''<form string="Sales Order">
<header><button name="action_confirm" type="object"/>
<field name="state" widget="statusbar" statusbar_visible="draft,sent,sale"/></header>
<sheet><div class="oe_button_box" name="button_box"/>
<div class="badge rounded-pill" invisible="not locked"><i class="fa fa-lock"/>Locked</div>
<div class="oe_title"><h1><field name="name"/></h1></div>
<group name="sale_header"><field name="partner_id"/></group>
<notebook><page name="order_lines"><field name="order_line"/></page></notebook>
</sheet></form>'''
LIST = '''<list string="Sales Orders"><header><button name="make_invoice" type="action"/></header>
<field name="name"/><field name="date_order"/><field name="partner_id"/>
<field name="amount_total"/><field name="tag_ids" optional="hide"/>
<field name="state" widget="badge" optional="hide"/>
<field name="invoice_status" optional="show"/>
<field name="client_order_ref" optional="hide"/></list>'''


def record_arch(xml_id):
    doc = etree.parse(str(ROOT / "views/sale_order_views.xml"))
    return doc.xpath(f"/odoo/record[@id='{xml_id}']/field[@name='arch']")[0]


def apply_specs(source, specs):
    root = etree.fromstring(source.encode()) if isinstance(source, str) else copy.deepcopy(source)
    for spec in specs:
        if not isinstance(spec.tag, str):
            continue
        if spec.tag != "xpath":
            raise AssertionError(f"Unexpected spec type: {spec.tag}")
        matches = root.xpath(spec.get("expr"))
        if len(matches) != 1:
            raise AssertionError(f"Expected one match: {spec.get('expr')} -> {len(matches)}")
        node = matches[0]
        position = spec.get("position")
        if position == "attributes":
            for item in spec:
                if item.tag == "attribute":
                    if item.get("add") is not None:
                        name = item.get("name")
                        old = node.get(name, "")
                        node.set(name, (old + item.get("separator", ",") if old else "") + item.get("add"))
                    else:
                        node.set(item.get("name"), item.text or "")
        elif position == "inside":
            for item in spec:
                node.append(copy.deepcopy(item))
        elif position in {"before", "after"}:
            parent = node.getparent()
            index = parent.index(node) + (position == "after")
            for item in spec:
                parent.insert(index, copy.deepcopy(item))
                index += 1
        else:
            raise AssertionError(f"Unsupported position: {position}")
    return root


class TestLayout(unittest.TestCase):
    def form(self):
        return apply_specs(FORM, record_arch("view_order_form_lock_control"))

    def order_list(self):
        return apply_specs(LIST, record_arch("view_order_list_lock_control"))

    def test_whole_order_line_widget_readonly_when_closed(self):
        node = self.form().xpath("//field[@name='order_line']")[0]
        self.assertEqual(node.get("readonly"), "locked")
        self.assertTrue(eval(node.get("readonly"), {}, {"locked": True}))
        self.assertFalse(eval(node.get("readonly"), {}, {"locked": False}))

    def test_existing_x2many_readonly_restrictions_preserved(self):
        source = FORM.replace('<field name="order_line"/>',
                              '<field name="order_line" readonly="state == \'cancel\'"/>')
        arch = apply_specs(source, record_arch("view_order_form_lock_control"))
        expr = arch.xpath("//field[@name='order_line']")[0].get("readonly")
        self.assertTrue(eval(expr, {}, {"state": "cancel", "locked": False}))
        self.assertTrue(eval(expr, {}, {"state": "sale", "locked": True}))
        self.assertFalse(eval(expr, {}, {"state": "sale", "locked": False}))

    def test_closing_prompt_requires_reopen(self):
        node = self.form().xpath("//button[@name='action_dvz_close']")[0]
        self.assertIn("reopens", node.get("confirm"))
        self.assertNotIn("Only authorized users will be able to edit", node.get("confirm"))

    def test_no_visible_header_status(self):
        fields = self.form().xpath("/form/header/field[@name='dvz_lock_status']")
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0].get("invisible"), "1")

    def test_no_header_badge_widget(self):
        self.assertFalse(self.form().xpath("/form/header/field[@name='dvz_lock_status'][@widget='badge']"))

    def test_two_ribbons_in_form_sheet_only(self):
        form = self.form()
        self.assertEqual(len(form.xpath("/form/sheet/widget[@name='web_ribbon']")), 2)
        self.assertFalse(form.xpath("/form/header/widget[@name='web_ribbon']"))

    def test_ribbons_precede_title_and_button_box(self):
        sheet = self.form().find("sheet")
        self.assertEqual(sheet[0].get("name"), "web_ribbon")
        self.assertEqual(sheet[1].get("name"), "web_ribbon")
        self.assertEqual(sheet[2].get("name"), "button_box")

    def test_closed_ribbon_red_and_driven_by_lock(self):
        node = self.form().xpath("/form/sheet/widget[@title='Closed']")[0]
        self.assertEqual(node.get("bg_color"), "text-bg-danger")
        self.assertEqual(node.get("invisible"), "not locked")

    def test_open_ribbon_green_and_driven_by_lock(self):
        node = self.form().xpath("/form/sheet/widget[@title='Open']")[0]
        self.assertEqual(node.get("bg_color"), "text-bg-success")
        self.assertEqual(node.get("invisible"), "locked")

    def test_exactly_one_ribbon_visible_in_each_state(self):
        for locked, expected in [(False, "Open"), (True, "Closed")]:
            visible = [r.get("title") for r in self.form().xpath("//widget[@name='web_ribbon']")
                       if not eval(r.get("invisible"), {"__builtins__": {}}, {"locked": locked})]
            self.assertEqual(visible, [expected])

    def test_ribbons_not_restricted_to_lock_managers(self):
        for node in self.form().xpath("//widget[@name='web_ribbon']"):
            self.assertIsNone(node.get("groups"))

    def test_existing_native_statusbar_unchanged(self):
        old = etree.fromstring(FORM.encode()).xpath("/form/header/field[@name='state']")[0]
        new = self.form().xpath("/form/header/field[@name='state']")[0]
        self.assertEqual(dict(new.attrib), dict(old.attrib))

    def test_lock_buttons_keep_same_permission_group(self):
        for name in ("action_dvz_close", "action_dvz_open"):
            node = self.form().xpath(f"/form/header/button[@name='{name}']")[0]
            self.assertEqual(node.get("groups"), "dvz_sale_order_lock.group_manage_locked_sale_orders")

    def test_hidden_helpers_retained(self):
        form = self.form()
        for name in ("locked", "dvz_can_manage_lock", "dvz_lock_readonly", "dvz_lock_status"):
            self.assertTrue(form.xpath(f"/form/header/field[@name='{name}'][@invisible='1']"))

    def test_list_status_immediately_after_native_state(self):
        fields = self.order_list().xpath("/list/field")
        names = [field.get("name") for field in fields]
        self.assertEqual(names[names.index("state") + 1], "dvz_lock_status")
        self.assertNotEqual(names[names.index("name") + 1], "dvz_lock_status")

    def test_only_one_list_status_field(self):
        self.assertEqual(len(self.order_list().xpath("/list/field[@name='dvz_lock_status']")), 1)

    def test_list_both_statuses_shown_by_default(self):
        for name in ("state", "dvz_lock_status"):
            field = self.order_list().xpath(f"/list/field[@name='{name}']")[0]
            self.assertEqual(field.get("optional"), "show")

    def test_existing_list_field_order_preserved(self):
        before = etree.fromstring(LIST.encode())
        names_before = [n.get("name") for n in before.xpath("/list/field")]
        names_after = [n.get("name") for n in self.order_list().xpath("/list/field") if n.get("name") != "dvz_lock_status"]
        self.assertEqual(names_after, names_before)

    def test_quotation_optional_overrides_preserve_status_adjacency(self):
        arch = self.order_list()
        arch.xpath("/list/field[@name='state']")[0].set("optional", "show")
        arch.xpath("/list/field[@name='invoice_status']")[0].set("optional", "hide")
        lock = arch.xpath("/list/field[@name='dvz_lock_status']")[0]
        self.assertEqual(lock.getprevious().get("name"), "state")

    def test_original_xml_ids_preserved_for_upgrade(self):
        doc = etree.parse(str(ROOT / "views/sale_order_views.xml"))
        self.assertEqual(set(doc.xpath("/odoo/record/@id")), {
            "view_order_form_lock_control", "view_order_list_lock_control", "view_order_search_lock_control",
        })

    def test_search_open_closed_and_group_unchanged(self):
        arch = record_arch("view_order_search_lock_control")
        for name, value in [("dvz_open_orders", "open"), ("dvz_closed_orders", "closed")]:
            node = arch.xpath(f".//filter[@name='{name}']")[0]
            self.assertEqual(ast.literal_eval(node.get("domain")), [("dvz_lock_status", "=", value)])
        node = arch.xpath(".//filter[@name='dvz_group_lock_status']")[0]
        self.assertEqual(ast.literal_eval(node.get("context")), {"group_by": "dvz_lock_status"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
