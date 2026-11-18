"""Execute the actual native salary-rule XML without an Odoo installation.

Run: python3 -m unittest discover -s qa -p 'test_native_rules.py' -v

This is not an Odoo integration test. The wrapper below supplies native-style
contract/input/category data, executes the shipped rule conditions and Python,
then applies the inspected upstream BASIC/GROSS/NET formulas. Expected amounts
are independent numerical fixtures, not a second benefit-calculation helper.
"""

from pathlib import Path
import re
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
RULE_TREE = ET.parse(ROOT / "data" / "salary_rules.xml").getroot()
STRUCTURE_TREE = ET.parse(ROOT / "data" / "salary_structure.xml").getroot()

# Verified against Odoo Mates 19.0, hr_payroll_data.xml, commit
# 828360acf884585c291f008713fe506da44147f9. These are native totals, not a
# reimplementation of any of the supplied benefit rules.
NATIVE_BASIC = "result = contract.wage"
NATIVE_GROSS = "result = categories.BASIC + categories.ALW"
NATIVE_NET = "result = categories.BASIC + categories.ALW + categories.DED"

RECURRING_FIELDS = {
    "DVZ_FUEL": "dvz_fuel_allowance",
    "DVZ_ACCOMMODATION": "dvz_accommodation_allowance",
    "DVZ_TRAVEL": "dvz_travel_allowance",
    "DVZ_MOBILE": "dvz_mobile_allowance",
    "DVZ_MEAL": "dvz_meal_allowance",
    "DVZ_SPECIAL_DUTY": "dvz_special_duty_allowance",
    "DVZ_CAR_MAINT": "dvz_car_maintenance_allowance",
    "DVZ_MEDICAL": "dvz_medical_allowance",
    "DVZ_AIR_TICKET": "dvz_air_ticket_allowance",
}
EARNING_CODES = (
    "DVZ_LEAVE_ENCASH", "DVZ_FUEL", "DVZ_ACCOMMODATION", "DVZ_EOSB",
    "DVZ_TRAVEL", "DVZ_EX_GRATIA", "DVZ_MOBILE", "DVZ_MEAL", "DVZ_OT",
    "DVZ_SPECIAL_DUTY", "DVZ_CAR_MAINT", "DVZ_MEDICAL", "DVZ_WELFARE",
    "DVZ_NOTICE", "DVZ_AIR_TICKET",
)


def text(record, name):
    node = record.find("field[@name='%s']" % name)
    return (node.text or "").strip() if node is not None else ""


RULES = sorted(
    RULE_TREE.findall(".//record[@model='hr.salary.rule']"),
    key=lambda record: int(text(record, "sequence")),
)
CATEGORY_CODES = {
    record.get("id"): text(record, "code")
    for record in RULE_TREE.findall(".//record[@model='hr.salary.rule.category']")
}


class Categories:
    def __init__(self):
        self.values = {}

    def __getattr__(self, key):
        return self.values.get(key, 0.0)

    def add(self, key, amount):
        self.values[key] = self.values.get(key, 0.0) + amount


class InputWrapper:
    """Minimal callback contract: exact code + employment-version matching."""

    def __init__(self, rows):
        self.rows = rows

    def _dvz_input_amount(self, code, version_id):
        return sum(amount for row_code, row_version, amount in self.rows
                   if row_code == code and row_version == version_id)


def contract_values(**changes):
    values = {
        "id": 11,
        "wage": 10000.0,
        "dvz_salary_base": "wage",
        "dvz_custom_salary_base": 0.0,
        "dvz_salary_days_divisor": 0.0,
        "dvz_hours_per_day": 0.0,
        "dvz_ot_multiplier": 0.0,
        "dvz_pf_enabled": False,
        "dvz_pf_base": "wage",
        "dvz_pf_custom_base": 0.0,
        "dvz_pf_employee_rate": 0.0,
        "dvz_pf_employer_rate": 0.0,
        "dvz_pf_employee_cap": 0.0,
        "dvz_pf_employer_cap": 0.0,
    }
    values.update({field: 0.0 for field in RECURRING_FIELDS.values()})
    values.update(changes)
    return SimpleNamespace(**values)


def calculate(contract=None, inputs=None, rows=None):
    contract = contract or contract_values()
    rows = list(rows or [])
    rows.extend((code, contract.id, amount) for code, amount in (inputs or {}).items())
    categories = Categories()
    context = {
        "contract": contract,
        "payslip": SimpleNamespace(dict=InputWrapper(rows)),
        "categories": categories,
        "result": 0.0,
    }
    allowed = {"__builtins__": {"min": min, "max": max, "float": float}}
    exec(NATIVE_BASIC, allowed, context)
    totals = {"BASIC": context["result"]}
    categories.add("BASIC", context["result"])
    for rule in RULES:
        context["result"] = False
        if text(rule, "condition_select") == "python":
            exec(text(rule, "condition_python"), allowed, context)
            if not context["result"]:
                continue
        context["result"] = 0.0
        context["result_qty"] = 1.0
        context["result_rate"] = 100.0
        exec(text(rule, "amount_python_compute"), allowed, context)
        amount = context["result"] * context["result_qty"] * context["result_rate"] / 100.0
        totals[text(rule, "code")] = amount
        category_reference = rule.find("field[@name='category_id']").get("ref")
        category = CATEGORY_CODES.get(category_reference, category_reference.split(".")[-1])
        categories.add(category, amount)
    exec(NATIVE_GROSS, allowed, context)
    totals["GROSS"] = context["result"]
    categories.add("GROSS", context["result"])
    exec(NATIVE_NET, allowed, context)
    totals["NET"] = context["result"]
    return totals, categories


class NativeRuleArithmeticTests(unittest.TestCase):
    def test_each_of_the_nine_recurring_allowances_uses_its_own_field(self):
        for number, (code, field) in enumerate(RECURRING_FIELDS.items(), 1):
            with self.subTest(code=code):
                amount = number * 100.0
                totals, _categories = calculate(contract_values(**{field: amount}))
                self.assertEqual(totals[code], amount)
                self.assertEqual(totals["NET"], 10000 + amount)
                self.assertEqual(set(totals) - {"BASIC", "GROSS", "NET"}, {code})

    def test_all_nine_recurring_allowances_enter_gross_and_net(self):
        fields = {field: number * 100.0 for number, field in enumerate(RECURRING_FIELDS.values(), 1)}
        totals, categories = calculate(contract_values(**fields))
        self.assertEqual(categories.ALW, 4500)
        self.assertEqual(totals["GROSS"], 14500)
        self.assertEqual(totals["NET"], 14500)

    def test_each_of_fifteen_earnings_accepts_its_native_cash_input(self):
        for code in EARNING_CODES:
            with self.subTest(code=code):
                totals, _categories = calculate(inputs={code: 37.25})
                self.assertEqual(totals[code], 37.25)
                self.assertEqual(totals["NET"], 10037.25)

    def test_all_cash_inputs_and_recurring_fields_combine_once(self):
        fields = {field: number * 100.0 for number, field in enumerate(RECURRING_FIELDS.values(), 1)}
        inputs = {code: number * 10.0 for number, code in enumerate(EARNING_CODES, 1)}
        totals, categories = calculate(contract_values(**fields), inputs)
        self.assertEqual(categories.ALW, 5700)
        self.assertEqual(totals["NET"], 15700)

    def test_recurring_plus_additional_cash_is_additive(self):
        totals, _categories = calculate(contract_values(dvz_fuel_allowance=500), {"DVZ_FUEL": 125})
        self.assertEqual(totals["DVZ_FUEL"], 625)
        self.assertEqual(totals["NET"], 10625)

    def test_leave_encashment_days_use_salary_basis(self):
        totals, _categories = calculate(
            contract_values(wage=6000, dvz_salary_days_divisor=30), {"DVZ_LEAVE_DAYS": 3.5}
        )
        self.assertEqual(totals["DVZ_LEAVE_ENCASH"], 700)
        self.assertEqual(totals["NET"], 6700)

    def test_leave_days_can_use_custom_salary_base(self):
        totals, _categories = calculate(
            contract_values(dvz_salary_base="custom", dvz_custom_salary_base=3600,
                            dvz_salary_days_divisor=30),
            {"DVZ_LEAVE_DAYS": 2.5},
        )
        self.assertEqual(totals["DVZ_LEAVE_ENCASH"], 300)

    def test_overtime_hours_use_configured_divisors_and_multiplier(self):
        totals, _categories = calculate(
            contract_values(wage=4800, dvz_salary_days_divisor=30,
                            dvz_hours_per_day=8, dvz_ot_multiplier=1.5),
            {"DVZ_OT_HOURS": 10},
        )
        self.assertEqual(totals["DVZ_OT"], 300)
        self.assertEqual(totals["NET"], 5100)

    def test_notice_days_are_an_employee_earning(self):
        totals, _categories = calculate(
            contract_values(wage=6000, dvz_salary_days_divisor=30), {"DVZ_NOTICE_DAYS": 5.5}
        )
        self.assertEqual(totals["DVZ_NOTICE"], 1100)
        self.assertEqual(totals["NET"], 7100)

    def test_cash_and_quantity_inputs_are_explicitly_additive(self):
        contract = contract_values(wage=4800, dvz_salary_days_divisor=30,
                                   dvz_hours_per_day=8, dvz_ot_multiplier=1.5)
        totals, _categories = calculate(contract, {
            "DVZ_LEAVE_ENCASH": 25, "DVZ_LEAVE_DAYS": 2,
            "DVZ_OT": 50, "DVZ_OT_HOURS": 10,
            "DVZ_NOTICE": 75, "DVZ_NOTICE_DAYS": 1,
        })
        self.assertEqual(totals["DVZ_LEAVE_ENCASH"], 345)
        self.assertEqual(totals["DVZ_OT"], 350)
        self.assertEqual(totals["DVZ_NOTICE"], 235)
        self.assertEqual(totals["NET"], 5730)

    def test_zero_inputs_and_zero_parameters_do_not_create_payments(self):
        totals, _categories = calculate(inputs={code: 0 for code in EARNING_CODES})
        self.assertEqual(totals, {"BASIC": 10000, "GROSS": 10000, "NET": 10000})

    def test_native_inputs_match_the_requested_version_and_exact_code(self):
        totals, _categories = calculate(rows=[
            ("DVZ_FUEL", 11, 100), ("DVZ_FUEL", 12, 900), ("DVZ_FUEL_EXTRA", 11, 777),
        ])
        self.assertEqual(totals["DVZ_FUEL"], 100)
        self.assertEqual(totals["NET"], 10100)

    def test_multiple_native_input_rows_for_one_code_are_summed(self):
        totals, _categories = calculate(rows=[("DVZ_FUEL", 11, 70), ("DVZ_FUEL", 11, 30)])
        self.assertEqual(totals["DVZ_FUEL"], 100)

    def test_pf_deduction_sign_and_employer_exclusion(self):
        totals, categories = calculate(contract_values(
            dvz_fuel_allowance=500, dvz_pf_enabled=True,
            dvz_pf_employee_rate=1, dvz_pf_employer_rate=1,
        ))
        self.assertEqual(totals["DVZ_PF_EMPLOYEE"], -100)
        self.assertEqual(totals["DVZ_PF_EMPLOYER"], 100)
        self.assertEqual(categories.DVZ_COMP, 100)
        self.assertEqual(totals["GROSS"], 10500)
        self.assertEqual(totals["NET"], 10400)

    def test_pf_disabled_ignores_configured_rates(self):
        totals, _categories = calculate(contract_values(
            dvz_pf_enabled=False, dvz_pf_employee_rate=5, dvz_pf_employer_rate=10,
        ))
        self.assertNotIn("DVZ_PF_EMPLOYEE", totals)
        self.assertNotIn("DVZ_PF_EMPLOYER", totals)
        self.assertEqual(totals["NET"], 10000)

    def test_pf_custom_base_is_independent_of_wage(self):
        totals, _categories = calculate(contract_values(
            dvz_pf_enabled=True, dvz_pf_base="custom", dvz_pf_custom_base=8000,
            dvz_pf_employee_rate=5, dvz_pf_employer_rate=7,
        ))
        self.assertEqual(totals["DVZ_PF_EMPLOYEE"], -400)
        self.assertEqual(totals["DVZ_PF_EMPLOYER"], 560)
        self.assertEqual(totals["GROSS"], 10000)
        self.assertEqual(totals["NET"], 9600)

    def test_pf_employee_and_employer_caps_are_independent(self):
        totals, _categories = calculate(contract_values(
            dvz_pf_enabled=True, dvz_pf_employee_rate=5, dvz_pf_employer_rate=9,
            dvz_pf_employee_cap=250, dvz_pf_employer_cap=300,
        ))
        self.assertEqual(totals["DVZ_PF_EMPLOYEE"], -250)
        self.assertEqual(totals["DVZ_PF_EMPLOYER"], 300)
        self.assertEqual(totals["NET"], 9750)

    def test_zero_pf_caps_mean_unlimited_and_zero_rates_do_not_pay(self):
        totals, _categories = calculate(contract_values(
            dvz_pf_enabled=True, dvz_pf_employee_rate=5, dvz_pf_employer_rate=0,
            dvz_pf_employee_cap=0,
        ))
        self.assertEqual(totals["DVZ_PF_EMPLOYEE"], -500)
        self.assertNotIn("DVZ_PF_EMPLOYER", totals)
        self.assertEqual(totals["NET"], 9500)


class NativeDefinitionTests(unittest.TestCase):
    def test_structure_links_all_seventeen_native_rules_and_inherits_native_totals(self):
        structures = STRUCTURE_TREE.findall(".//record[@model='hr.payroll.structure']")
        self.assertEqual(len(structures), 1)
        structure = structures[0]
        self.assertEqual(structure.find("field[@name='parent_id']").get("ref"), "om_hr_payroll.structure_base")
        expression = structure.find("field[@name='rule_ids']").get("eval")
        references = re.findall(r"ref\(['\"]([^'\"]+)['\"]\)", expression)
        self.assertEqual(len(references), 17)
        self.assertEqual(set(references), {rule.get("id") for rule in RULES})
        self.assertEqual(len({text(rule, "code") for rule in RULES}), 17)

    def test_eighteen_native_inputs_have_unique_codes_and_valid_rule_owners(self):
        inputs = RULE_TREE.findall(".//record[@model='hr.rule.input']")
        self.assertEqual(len(inputs), 18)
        self.assertEqual(
            {text(item, "code") for item in inputs},
            set(EARNING_CODES) | {"DVZ_LEAVE_DAYS", "DVZ_OT_HOURS", "DVZ_NOTICE_DAYS"},
        )
        rule_ids = {rule.get("id") for rule in RULES}
        for item in inputs:
            self.assertIn(item.find("field[@name='input_id']").get("ref"), rule_ids)

    def test_employer_category_has_no_salary_parent(self):
        employer = next(rule for rule in RULES if text(rule, "code") == "DVZ_PF_EMPLOYER")
        reference = employer.find("field[@name='category_id']").get("ref")
        category = RULE_TREE.find(".//record[@id='%s']" % reference)
        self.assertEqual(text(category, "code"), "DVZ_COMP")
        self.assertEqual(category.find("field[@name='parent_id']").get("eval"), "False")
        self.assertNotIn("DVZ_COMP", NATIVE_GROSS)
        self.assertNotIn("DVZ_COMP", NATIVE_NET)

    def test_native_rules_use_ordered_unique_codes_and_preserve_admin_edits(self):
        self.assertTrue(all(20 <= int(text(rule, "sequence")) < 100 for rule in RULES))
        self.assertEqual(RULE_TREE.find("data").get("noupdate"), "1")
        self.assertEqual(STRUCTURE_TREE.find("data").get("noupdate"), "1")
        for rule in RULES:
            self.assertEqual(rule.get("model"), "hr.salary.rule")
            self.assertEqual(rule.find("field[@name='dvz_benefit_rule']").get("eval"), "True")


if __name__ == "__main__":
    unittest.main()
