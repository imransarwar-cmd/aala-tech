"""Validate this native Odoo addon without importing or running Odoo.

Run from any working directory: python3 qa/validate_package.py
This checks packaging, Python/XML syntax, local XML references, native rule
definitions, and the absence of custom benefit models. It cannot validate the
Odoo registry, views against a live database, ACLs, or actual payroll execution.
"""

import ast
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def validate():
    errors = []
    manifest_path = ROOT / "__manifest__.py"
    if not manifest_path.exists():
        return ["Missing __manifest__.py"], {}
    try:
        manifest = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, SyntaxError) as exc:
        return ["Invalid manifest: %s" % exc], {}
    if "om_hr_payroll" not in manifest.get("depends", []):
        errors.append("The manifest must depend on om_hr_payroll.")
    if not str(manifest.get("version", "")).startswith("19.0."):
        errors.append("The addon version must target Odoo 19.0.")
    if not manifest.get("installable"):
        errors.append("The addon must be installable.")

    python_files = sorted(ROOT.rglob("*.py"))
    for path in python_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append("Python syntax error in %s: %s" % (path.relative_to(ROOT), exc))
            continue
        if path.parent.name == "models":
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    targets = [item.id for item in node.targets if isinstance(item, ast.Name)]
                    if "_name" in targets and isinstance(node.value, ast.Constant):
                        name = node.value.value
                        if isinstance(name, str) and name.startswith("dvz.benefit."):
                            errors.append("Custom benefit model is not allowed in native edition: %s" % name)

    records = {}
    roots = []
    declared_xml = []
    for filename in manifest.get("data", []):
        path = ROOT / filename
        if not path.is_file():
            errors.append("Manifest data file is missing: %s" % filename)
            continue
        if "wizard" in str(filename):
            errors.append("Native edition must not load a benefit setup wizard: %s" % filename)
        if path.suffix != ".xml":
            continue
        declared_xml.append(path)
        try:
            xml_root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            errors.append("XML syntax error in %s: %s" % (filename, exc))
            continue
        roots.append((filename, xml_root))
        if xml_root.tag != "odoo":
            errors.append("XML root must be <odoo>: %s" % filename)
        for node in xml_root.iter():
            if node.get("attrs") is not None or node.get("states") is not None:
                errors.append("Legacy attrs/states view modifier found in %s" % filename)
            identifier = node.get("id")
            if identifier and node.tag in ("record", "menuitem", "template"):
                if identifier in records:
                    errors.append("Duplicate XML id: %s" % identifier)
                records[identifier] = node
            if node.get("model", "").startswith("dvz.benefit."):
                errors.append("Custom benefit model record found in %s" % filename)

    def check_reference(reference, filename):
        if reference.startswith("dvz_employee_benefits."):
            reference = reference.split(".", 1)[1]
        elif "." in reference:
            return
        if reference not in records:
            errors.append("Unresolved local XML reference %s in %s" % (reference, filename))

    for filename, xml_root in roots:
        for node in xml_root.iter():
            if node.get("ref"):
                check_reference(node.get("ref"), filename)
            for reference in re.findall(r"\bref\(['\"]([^'\"]+)['\"]\)", node.get("eval", "")):
                check_reference(reference, filename)
            if node.tag == "menuitem":
                for attribute in ("parent", "action"):
                    if node.get(attribute):
                        check_reference(node.get(attribute), filename)

    rules = {
        identifier: node for identifier, node in records.items()
        if node.get("model") == "hr.salary.rule"
    }
    if len(rules) != 17:
        errors.append("Expected 17 native benefit rules; found %s." % len(rules))
    codes = []
    for identifier, rule in rules.items():
        fields = {node.get("name"): node for node in rule.findall("field")}
        code = (fields.get("code").text or "").strip() if "code" in fields else ""
        codes.append(code)
        if not code:
            errors.append("Salary rule has no code: %s" % identifier)
        if "category_id" not in fields:
            errors.append("Salary rule has no category: %s" % identifier)
        amount_mode = (fields.get("amount_select").text or "").strip() if "amount_select" in fields else ""
        if amount_mode != "code":
            errors.append("Expected native Python salary rule: %s" % identifier)
        for name in ("condition_python", "amount_python_compute"):
            if name in fields and fields[name].text:
                try:
                    compile(fields[name].text.strip(), "%s:%s" % (identifier, name), "exec")
                except SyntaxError as exc:
                    errors.append("Invalid rule Python for %s: %s" % (identifier, exc))
    if len(set(codes)) != len(codes):
        errors.append("Salary rule codes are not unique.")

    inputs = [node for node in records.values() if node.get("model") == "hr.rule.input"]
    for item in inputs:
        owner = item.find("field[@name='input_id']")
        if owner is None or owner.get("ref", "").split(".")[-1] not in rules:
            errors.append("Native input must be attached to one supplied salary rule: %s" % item.get("id"))

    structures = [node for node in records.values() if node.get("model") == "hr.payroll.structure"]
    if not structures:
        errors.append("Missing native salary structure.")
    else:
        linked = set()
        for structure in structures:
            for item in structure.findall("field[@name='rule_ids']"):
                linked.update(
                    reference.split(".")[-1]
                    for reference in re.findall(r"\bref\(['\"]([^'\"]+)['\"]\)", item.get("eval", ""))
                )
        missing = set(rules) - linked
        if missing:
            errors.append("Native salary structure is missing benefit rules: %s" % ", ".join(sorted(missing)))

    return errors, {
        "python_files": len(python_files), "xml_files": len(declared_xml),
        "native_salary_rules": len(rules), "native_inputs": len(inputs),
        "native_structures": len(structures),
    }


if __name__ == "__main__":
    issues, counts = validate()
    if issues:
        for issue in issues:
            print("ERROR:", issue)
        sys.exit(1)
    print("Static package validation passed:", counts)
    print("Odoo runtime installation and integration tests are separate and have not been run here.")
