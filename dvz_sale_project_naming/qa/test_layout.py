"""Pure XML tests: no live Odoo registry or browser is exercised here."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dvz_layout_pure', ROOT/'layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)

TARGET = '''<group name="dvz_project_information" string="Project Information" col="2">
  <group name="dvz_project_information_left"><field name="dvz_division_id"/></group>
  <group name="dvz_project_information_right"/>
</group>'''


def form(contents='', extra=''):
    return etree.fromstring(f'<form><sheet>{contents}{TARGET}{extra}<notebook><page name="other_information"/></notebook></sheet><chatter/></form>')


def metadata(name='x_studio_system', label='System', type_='char'):
    return {name: {'string': label, 'type': type_}}


def field(arch, name):
    return arch.xpath('.//field[@name=$name]', name=name)[0]


def destination_names(arch, side='left'):
    return arch.xpath(f"./sheet/group[@name='{layout.GROUP}']/group[@name='dvz_project_information_{side}']//field/@name")


class TestProjectInformationLayout(unittest.TestCase):
    def test_full_screenshot_layout_all_eight_roles(self):
        labels = [('x_system','System','char'), ('x_project','Project','char'),
                  ('x_brand','Brand','many2many'), ('x_area','Area','many2many'),
                  ('x_priority','Priority','selection'), ('x_engineer','Estimation Engineer','many2one'),
                  ('x_remarks','Remarks','text'), ('x_logo','Client/Product Logo','binary')]
        meta = {n: {'string': s, 'type': t} for n,s,t in labels}
        nodes = ''.join(f'<field name="{n}"/>' for n,_,_ in labels)
        arch = form(f'<group name="old_custom">{nodes}</group>')
        result = layout.regroup_project_fields(arch, meta)
        self.assertEqual(len(result['moved']), 8)
        self.assertFalse(result['skipped'])
        self.assertFalse(result['missing'])
        self.assertEqual(destination_names(arch), ['dvz_division_id', 'x_system', 'x_project', 'x_brand', 'x_area', 'x_priority'])
        self.assertEqual(destination_names(arch, 'right'), ['x_engineer', 'x_remarks', 'x_logo'])
        self.assertFalse(arch.xpath(".//group[@name='old_custom']"))

    def test_division_directly_before_system(self):
        arch = form('<group><field name="x_studio_system"/></group>')
        layout.regroup_project_fields(arch, metadata())
        self.assertEqual(destination_names(arch)[:2], ['dvz_division_id', 'x_studio_system'])

    def test_existing_field_node_is_moved_not_recreated(self):
        arch = form('<group><field name="x_studio_system"/></group>')
        original = field(arch, 'x_studio_system')
        layout.regroup_project_fields(arch, metadata())
        self.assertIs(original, field(arch, 'x_studio_system'))
        self.assertEqual(len(arch.xpath(".//field[@name='x_studio_system']")), 1)

    def test_readonly_domain_options_widget_and_context_preserved(self):
        arch = form('''<group><field name="x_studio_system" widget="many2many_tags"
          readonly="state == 'sale'" domain="[('active', '=', True)]" options="{'no_create': True}"
          required="state == 'draft'" context="{'default_active': True}" groups="base.group_user"/></group>''')
        original_attrs = dict(field(arch, 'x_studio_system').attrib)
        layout.regroup_project_fields(arch, metadata(type_='many2many'))
        self.assertEqual(dict(field(arch, 'x_studio_system').attrib), original_attrs)

    def test_opaque_studio_field_uses_metadata_label(self):
        arch = form('<group><field name="x_studio_char_7bf_d92"/></group>')
        result = layout.regroup_project_fields(arch, metadata('x_studio_char_7bf_d92'))
        self.assertEqual(result['moved']['system'], 'x_studio_char_7bf_d92')

    def test_xml_label_overrides_opaque_metadata(self):
        arch = form('<group><field name="x_data" string="System"/></group>')
        result = layout.regroup_project_fields(arch, metadata('x_data', 'Opaque'))
        self.assertIn('system', result['moved'])

    def test_technical_name_fallback(self):
        arch = form('<group><field name="x_studio_system_ids"/></group>')
        result = layout.regroup_project_fields(arch, metadata('x_studio_system_ids', 'Translated', 'many2many'))
        self.assertIn('system', result['moved'])

    def test_explicit_logo_label_and_image_wrapper_move_together(self):
        arch = form('''<group><label for="logo_widget" string="Client/Product Logo"/>
          <div class="image_holder"><field name="x_image" id="logo_widget" widget="image" nolabel="1"
          options="{'size': [128, 128]}"/></div></group>''')
        result = layout.regroup_project_fields(arch, metadata('x_image', 'Unknown', 'binary'))
        self.assertIn('logo', result['moved'])
        right = arch.xpath(".//group[@name='dvz_project_information_right']")[0]
        self.assertEqual(right[0].tag, 'label')
        self.assertEqual(right[1].tag, 'div')
        self.assertEqual(right[1][0].get('widget'), 'image')

    def test_nested_ancestor_group_security_preserved_separately(self):
        arch = form('''<group groups="sales_team.group_sale_manager"><group groups="!base.group_system">
          <field name="x_studio_system"/></group></group>''')
        layout.regroup_project_fields(arch, metadata())
        node = field(arch, 'x_studio_system')
        groups = [parent.get('groups') for parent in node.iterancestors() if parent.get('groups')]
        self.assertEqual(groups, ['!base.group_system', 'sales_team.group_sale_manager'])

    def test_ancestor_dynamic_invisibility_preserved(self):
        arch = form('''<group invisible="state == 'cancel'"><field name="x_studio_system"/></group>''')
        layout.regroup_project_fields(arch, metadata())
        self.assertEqual(field(arch, 'x_studio_system').getparent().get('invisible'), "state == 'cancel'")

    def test_ancestor_css_visibility_preserved(self):
        arch = form('<group class="d-none"><field name="x_studio_system"/></group>')
        layout.regroup_project_fields(arch, metadata())
        self.assertEqual(field(arch, 'x_studio_system').getparent().get('class'), 'd-none')

    def test_field_own_invisible_constant_not_moved(self):
        arch = form('<group name="source"><field name="x_studio_system" invisible="1"/></group>')
        layout.regroup_project_fields(arch, metadata())
        self.assertEqual(field(arch, 'x_studio_system').getparent().get('name'), 'source')

    def test_hidden_ancestor_not_moved(self):
        arch = form('<group name="source" invisible="True"><field name="x_studio_system"/></group>')
        layout.regroup_project_fields(arch, metadata())
        self.assertEqual(field(arch, 'x_studio_system').getparent().get('name'), 'source')

    def test_order_line_fields_never_moved(self):
        arch = form('<field name="order_line"><list><field name="x_studio_system"/></list></field>')
        result = layout.regroup_project_fields(arch, metadata())
        self.assertNotIn('system', result['moved'])
        self.assertEqual(field(arch, 'x_studio_system').getparent().tag, 'list')

    def test_notebook_fields_never_moved(self):
        arch = form(extra='<notebook><page><group><field name="x_studio_system"/></group></page></notebook>')
        result = layout.regroup_project_fields(arch, metadata())
        self.assertNotIn('system', result['moved'])

    def test_native_project_relation_left_untouched(self):
        arch = form('<group name="original"><field name="project_id" string="Project"/></group>')
        result = layout.regroup_project_fields(arch, metadata('project_id', 'Project', 'many2one'))
        self.assertNotIn('project', result['moved'])

    def test_unknown_field_left_untouched(self):
        arch = form('<group name="original"><field name="x_other" string="Other Details"/></group>')
        result = layout.regroup_project_fields(arch, metadata('x_other', 'Other Details'))
        self.assertFalse(result['moved'])
        self.assertEqual(field(arch, 'x_other').getparent().get('name'), 'original')

    def test_wrong_field_type_not_moved(self):
        arch = form('<group name="original"><field name="x_studio_system"/></group>')
        result = layout.regroup_project_fields(arch, metadata(type_='binary'))
        self.assertNotIn('system', result['moved'])

    def test_missing_metadata_not_guessed(self):
        arch = form('<group name="original"><field name="x_studio_system"/></group>')
        result = layout.regroup_project_fields(arch, {})
        self.assertFalse(result['moved'])

    def test_ambiguous_two_fields_with_same_label_skipped(self):
        arch = form('<group><field name="x_one"/><field name="x_two"/></group>')
        meta = {**metadata('x_one'), **metadata('x_two')}
        result = layout.regroup_project_fields(arch, meta)
        self.assertEqual(result['skipped']['system'], 'ambiguous field match')
        self.assertEqual(destination_names(arch), ['dvz_division_id'])

    def test_conflicting_labels_cannot_move_field_twice(self):
        arch = form('<group><field name="x_studio_system" string="Project"/></group>')
        result = layout.regroup_project_fields(arch, metadata())
        self.assertFalse(result['moved'])
        self.assertIn('system', result['skipped'])
        self.assertIn('project', result['skipped'])

    def test_wrapper_with_multiple_fields_is_not_split(self):
        arch = form('<group><div><field name="x_studio_system"/><field name="x_other"/></div></group>')
        result = layout.regroup_project_fields(arch, metadata())
        self.assertEqual(result['skipped']['system'], 'wrapper contains other fields')

    def test_unsupported_table_wrapper_left_in_place(self):
        arch = form('<table><tr><td><field name="x_studio_system"/></td></tr></table>')
        result = layout.regroup_project_fields(arch, metadata())
        self.assertIn('system', result['skipped'])

    def test_templated_ancestor_not_moved(self):
        arch = form('<group t-if="flag"><field name="x_studio_system"/></group>')
        result = layout.regroup_project_fields(arch, metadata())
        self.assertEqual(result['skipped']['system'], 'templated container')

    def test_legacy_modifier_ancestor_not_moved(self):
        arch = form('<group modifiers="{}"><field name="x_studio_system"/></group>')
        result = layout.regroup_project_fields(arch, metadata())
        self.assertIn('system', result['skipped'])

    def test_repeated_transform_is_idempotent(self):
        arch = form('<group><field name="x_studio_system"/></group>')
        layout.regroup_project_fields(arch, metadata())
        first = etree.tostring(arch)
        layout.regroup_project_fields(arch, metadata())
        self.assertEqual(etree.tostring(arch), first)

    def test_no_target_group_is_noop(self):
        arch = etree.fromstring('<form><sheet><group><field name="x_studio_system"/></group></sheet></form>')
        before = etree.tostring(arch)
        self.assertFalse(layout.regroup_project_fields(arch, metadata())['moved'])
        self.assertEqual(etree.tostring(arch), before)

    def test_non_form_is_noop(self):
        arch = etree.fromstring('<list><field name="x_studio_system"/></list>')
        before = etree.tostring(arch)
        layout.regroup_project_fields(arch, metadata())
        self.assertEqual(etree.tostring(arch), before)

    def test_native_anchor_groups_are_preserved(self):
        arch = form('<group name="sale_header"><group name="partner_details"><field name="x_studio_system"/></group></group>')
        layout.regroup_project_fields(arch, metadata())
        self.assertTrue(arch.xpath(".//group[@name='partner_details']"))
        self.assertTrue(arch.xpath(".//group[@name='sale_header']"))

    def test_unknown_sibling_is_preserved_in_source_group(self):
        arch = form('<group name="old"><field name="x_studio_system"/><field name="x_other"/></group>')
        layout.regroup_project_fields(arch, metadata())
        self.assertEqual(field(arch, 'x_other').getparent().get('name'), 'old')

    def test_explicit_label_from_different_group_is_not_orphaned(self):
        arch = form('<group><label for="x_studio_system"/></group><group><field name="x_studio_system"/></group>')
        result = layout.regroup_project_fields(arch, metadata())
        self.assertEqual(result['skipped']['system'], 'label is outside the field row')

    def test_main_sheet_field_direct_child_supported(self):
        arch = form('<field name="x_studio_system"/>')
        result = layout.regroup_project_fields(arch, metadata())
        self.assertIn('system', result['moved'])

    def test_no_record_data_or_security_rule_mutation_in_helper(self):
        source = (ROOT/'layout.py').read_text()
        self.assertNotIn('self.env', source)
        self.assertNotIn('.sudo(', source)
        self.assertNotIn('execute(', source)
        self.assertNotIn("'ir.rule'", source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
