"""Conservative, database-independent sales-form layout transformation.

Run on the combined architecture BEFORE Odoo's group/access postprocessing.
Existing field XML is moved, never recreated. Unknown/ambiguous fields remain
where they were. This helper has no ORM writes and never changes business data.
"""
from __future__ import annotations

from collections import Counter
import re
from typing import Mapping

from lxml import etree

GROUP = 'dvz_project_information'
LEFT = 'dvz_project_information_left'
RIGHT = 'dvz_project_information_right'

# Exact normalized labels, not broad substring guesses. A custom field with an
# opaque Studio technical name can therefore be recognized from its label.
ROLES = (
    ('system', LEFT, {'system', 'systems'}, {'char', 'text', 'selection', 'many2one', 'many2many'}),
    ('project', LEFT, {'project', 'project name', 'project title', 'project description'},
     {'char', 'text', 'html', 'many2one'}),
    ('brand', LEFT, {'brand', 'brands'}, {'char', 'selection', 'many2one', 'many2many'}),
    ('area', LEFT, {'area', 'areas'}, {'char', 'selection', 'many2one', 'many2many'}),
    ('priority', LEFT, {'priority', 'project priority'}, {'selection', 'char', 'many2one'}),
    ('estimation_engineer', RIGHT, {'estimation engineer', 'estimating engineer', 'estimator'},
     {'many2one', 'many2many', 'char'}),
    ('remarks', RIGHT, {'remarks', 'project remarks'}, {'char', 'text', 'html'}),
    ('logo', RIGHT, {'client product logo', 'client logo', 'product logo', 'customer logo'}, {'binary'}),
)
GUARD_ATTRIBUTES = ('groups', 'invisible', 'readonly', 'required')
NATIVE_EXCLUSIONS = {
    'project_id', 'project_ids', 'note', 'partner_id', 'partner_invoice_id',
    'partner_shipping_id', 'user_id', 'team_id', 'tag_ids', 'name', 'order_line',
}
PROTECTED_CONTAINERS = {'sale_header', 'partner_details', 'order_details'}
TRUE_VALUES = {'1', 'true'}


def normalize_label(value: str | None) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (value or '').casefold()).strip()


def _technical_label(name: str) -> str:
    for prefix in ('x_studio_', 'x_'):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    for suffix in ('_ids', '_id'):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return normalize_label(name)


def _is_main_field(node, sheet) -> bool:
    """Only fields of this sales order on the main sheet, not nested models/tabs."""
    if not node.get('name') or node.get('name').startswith('dvz_'):
        return False
    if node.get('name') in NATIVE_EXCLUSIONS:
        return False
    if node.get('invisible', '').strip().casefold() in TRUE_VALUES:
        return False
    for parent in node.iterancestors():
        if parent is sheet:
            return True
        if parent.tag in ('field', 'notebook', 'page', 'header', 'chatter'):
            return False
        if parent.get('name') == GROUP:
            return False
        if parent.get('invisible', '').strip().casefold() in TRUE_VALUES:
            return False
    return False


def _labels(node, sheet, metadata: Mapping[str, Mapping]) -> set[str]:
    name = node.get('name')
    values = [node.get('string'), metadata.get(name, {}).get('string'), _technical_label(name)]
    # Explicit labels are often used by Studio, especially for image fields.
    identifiers = {name, node.get('id')} - {None}
    for label in sheet.iter('label'):
        if label.get('for') in identifiers and not any(
            ancestor.tag in ('field', 'notebook', 'page') for ancestor in label.iterancestors()
        ):
            values.append(label.get('string'))
    return {normalize_label(value) for value in values if value}


def _scope_guards(unit, sheet):
    """Preserve each ancestor's guards separately: groups are ANDed, not ORed."""
    scopes = []
    for parent in unit.iterancestors():
        if parent is sheet:
            break
        if any(str(key).startswith('t-') for key in parent.attrib):
            raise ValueError('templated container')
        if any(key in parent.attrib for key in ('attrs', 'modifiers')):
            raise ValueError('legacy or postprocessed container')
        attrs = {key: parent.get(key) for key in GUARD_ATTRIBUTES if parent.get(key) is not None}
        # Preserve CSS visibility gates without duplicating a container's IDs.
        classes = [part for part in parent.get('class', '').split()
                   if part in {'d-none', 'invisible', 'oe_read_only', 'oe_edit_only'}]
        if classes:
            attrs['class'] = ' '.join(classes)
        if re.search(r'(display\s*:\s*none|visibility\s*:\s*hidden)', parent.get('style', ''), re.I):
            attrs['style'] = parent.get('style')
        if attrs:
            scopes.append(attrs)
    return list(reversed(scopes))


def _move_unit(node, sheet):
    """Keep a field's single-field HTML widget wrapper and explicit label intact."""
    unit = node
    while unit.getparent() is not None and unit.getparent() is not sheet:
        parent = unit.getparent()
        if parent.tag == 'group':
            break
        if parent.tag not in {'div', 'span', 'p'}:
            raise ValueError('unsupported field container')
        # Never move an unrelated field or a second widget along with this one.
        if len(list(parent.iter('field'))) != 1:
            raise ValueError('wrapper contains other fields')
        unit = parent
    if unit.getparent() is sheet and unit is node:
        # Direct sheet fields are valid too; the destination gives them a label.
        pass
    parent = unit.getparent()
    if parent is None:
        raise ValueError('detached field')
    identifiers = {node.get('name'), node.get('id')} - {None}
    label_units = []
    for sibling in parent:
        if sibling is unit:
            continue
        labels = list(sibling.iter('label'))
        matching = [label for label in labels if label.get('for') in identifiers]
        if not matching:
            continue
        if sibling.tag == 'label':
            label_units.append(sibling)
        elif sibling.tag in {'div', 'span'} and len(labels) == len(matching) and not list(sibling.iter('field')):
            # An explicit label-only wrapper (e.g. o_td_label).
            if sibling.xpath('.//button | .//a | .//input'):
                raise ValueError('label wrapper includes controls')
            label_units.append(sibling)
        else:
            raise ValueError('label shares a container')
    if len(label_units) > 1:
        raise ValueError('multiple external labels')
    # An outside label not in the same row cannot be safely moved automatically.
    internal_labels = set(unit.iter('label'))
    included_labels = {label for item in label_units for label in item.iter('label')}
    for label in sheet.iter('label'):
        if label.get('for') in identifiers and label not in internal_labels | included_labels:
            if any(a.tag in {'field', 'notebook', 'page'} for a in label.iterancestors()):
                continue
            raise ValueError('label is outside the field row')
    return [*label_units, unit], _scope_guards(unit, sheet)


def _prune_empty_containers(ancestors, sheet):
    """Remove only emptied layout wrappers on the paths from moved widgets."""
    for node in ancestors:
        if node is sheet or node.getparent() is None:
            continue
        if node.tag not in {'div', 'span', 'group'}:
            continue
        if node.get('name') in PROTECTED_CONTAINERS:
            continue
        if len(node) or (node.text or '').strip():
            continue
        if any(key.startswith('t-') for key in node.attrib):
            continue
        node.getparent().remove(node)


def regroup_project_fields(arch, metadata: Mapping[str, Mapping]) -> dict:
    """Move safely identified custom widgets into Project Information in place.

    Returns a report for logging/tests. No missing role creates a replacement
    field. A repeated/ambiguous widget is left alone rather than guessed.
    """
    report = {'moved': {}, 'skipped': {}, 'missing': []}
    sheets = arch.xpath('./sheet') if arch.tag == 'form' else []
    if len(sheets) != 1:
        return report
    sheet = sheets[0]
    groups = sheet.xpath("./group[@name=$name]", name=GROUP)
    if len(groups) != 1:
        return report
    target = groups[0]
    destinations = {}
    for name in (LEFT, RIGHT):
        matches = target.xpath('./group[@name=$name]', name=name)
        if len(matches) != 1:
            return report
        destinations[name] = matches[0]
    candidates = [node for node in sheet.iter('field') if _is_main_field(node, sheet)]
    matches_by_role = {}
    for role, _destination, accepted, types in ROLES:
        matches_by_role[role] = [
            node for node in candidates
            if metadata.get(node.get('name'), {}).get('type') in types
            and _labels(node, sheet, metadata) & accepted
        ]
    # A field whose label and technical name disagree must not get moved twice.
    references = Counter(id(node) for nodes in matches_by_role.values() for node in nodes)
    for role, destination_name, _accepted, _types in ROLES:
        matches = matches_by_role[role]
        if not matches:
            report['missing'].append(role)
            continue
        if len(matches) != 1 or references[id(matches[0])] != 1:
            report['skipped'][role] = 'ambiguous field match'
            continue
        node = matches[0]
        try:
            units, guards = _move_unit(node, sheet)
        except ValueError as exc:
            report['skipped'][role] = str(exc)
            continue
        old_ancestors = list(units[-1].iterancestors())
        destination = destinations[destination_name]
        if guards:
            for attrs in guards:
                scope = etree.SubElement(destination, 'group', col='2', colspan='2')
                scope.attrib.update(attrs)
                destination = scope
        for unit in units:
            destination.append(unit)
        _prune_empty_containers(old_ancestors, sheet)
        report['moved'][role] = node.get('name')
    return report
