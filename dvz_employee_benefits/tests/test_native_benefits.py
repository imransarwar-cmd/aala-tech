"""Real Odoo Mates integration tests; supplied but not run in this build.

Run on an Odoo 19 staging database with --test-tags /dvz_employee_benefits.
The employee/version fixture follows the inspected upstream 19.0 payroll tests.
"""

from datetime import date

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNativeBenefits(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.structure = cls.env.ref("dvz_employee_benefits.dvz_salary_structure")
        cls.company = cls.structure.company_id
        cls.calendar = cls.env["resource.calendar"].with_company(cls.company).create({
            "name": "DVZ Native Test Calendar", "company_id": cls.company.id, "tz": "UTC",
        })

    def _employee(self, wage=10000.0, **version_values):
        employee = self.env["hr.employee"].with_company(self.company).create({
            "name": "Native Benefit Test Employee",
            "company_id": self.company.id,
            "resource_calendar_id": self.calendar.id,
            "tz": "UTC",
            "date_version": date(2026, 1, 1),
            "contract_date_start": date(2026, 1, 1),
            "wage": wage,
        })
        employee.version_id.write({"struct_id": self.structure.id, **version_values})
        return employee

    def _payslip(self, employee):
        payslips = self.env["hr.payslip"].with_company(self.company)
        start, end = date(2026, 6, 1), date(2026, 6, 30)
        defaults = payslips.onchange_employee_id(start, end, employee.id)["value"]
        return payslips.create({
            "name": defaults.get("name") or "Native Benefit Test Payslip",
            "employee_id": employee.id,
            "company_id": self.company.id,
            "version_id": employee.version_id.id,
            "struct_id": employee.version_id.struct_id.id,
            "date_from": start, "date_to": end,
            "worked_days_line_ids": [
                Command.create(item) for item in defaults.get("worked_days_line_ids", [])
            ],
            "input_line_ids": [
                Command.create(item) for item in defaults.get("input_line_ids", [])
            ],
        })

    def _input(self, slip, code, amount, version=None, append=False):
        version = version or slip.version_id
        lines = slip.input_line_ids.filtered(
            lambda line: line.code == code and line.version_id == version
        )
        if lines and not append:
            lines[:1].amount = amount
            return lines[:1]
        return self.env["hr.payslip.input"].create({
            "payslip_id": slip.id, "version_id": version.id,
            "name": code, "code": code, "amount": amount,
        })

    @staticmethod
    def _totals(slip):
        return {line.code: round(line.total, 2) for line in slip.line_ids}

    def test_native_pf_rules_keep_employer_contribution_out_of_net(self):
        employee = self._employee(
            dvz_fuel_allowance=500, dvz_pf_enabled=True,
            dvz_pf_employee_rate=1, dvz_pf_employer_rate=1,
        )
        slip = self._payslip(employee)
        slip.compute_sheet()
        totals = self._totals(slip)
        self.assertEqual(totals["DVZ_PF_EMPLOYEE"], -100)
        self.assertEqual(totals["DVZ_PF_EMPLOYER"], 100)
        self.assertEqual(totals["GROSS"], 10500)
        self.assertEqual(totals["NET"], 10400)

    def test_native_cash_and_quantity_inputs_are_added_by_the_rules(self):
        employee = self._employee(
            wage=4800, dvz_salary_days_divisor=30,
            dvz_hours_per_day=8, dvz_ot_multiplier=1.5,
        )
        slip = self._payslip(employee)
        for code, amount in {
            "DVZ_LEAVE_ENCASH": 25, "DVZ_LEAVE_DAYS": 2,
            "DVZ_OT": 50, "DVZ_OT_HOURS": 10,
            "DVZ_NOTICE": 75, "DVZ_NOTICE_DAYS": 1,
            "DVZ_EOSB": 1000,
        }.items():
            self._input(slip, code, amount)
        slip.compute_sheet()
        totals = self._totals(slip)
        self.assertEqual(totals["DVZ_LEAVE_ENCASH"], 345)
        self.assertEqual(totals["DVZ_OT"], 350)
        self.assertEqual(totals["DVZ_NOTICE"], 235)
        self.assertEqual(totals["DVZ_EOSB"], 1000)
        self.assertEqual(totals["NET"], 6730)

    def test_inherited_inputs_and_recompute_preserve_existing_native_rows(self):
        child = self.env["hr.payroll.structure"].create({
            "name": "Native Benefits Child Structure", "code": "DVZ_TEST_CHILD",
            "company_id": self.company.id, "parent_id": self.structure.id,
            "rule_ids": [Command.set([])],
        })
        employee = self._employee(dvz_fuel_allowance=500)
        employee.version_id.struct_id = child
        slip = self._payslip(employee)
        # get_inputs must include the definitions inherited from the parent,
        # without adding duplicate zero rows or overwriting an existing amount.
        benefit_inputs = slip.input_line_ids.filtered(lambda line: line.code.startswith("DVZ_"))
        self.assertEqual(len(benefit_inputs), 18)
        self.assertEqual(len(set(benefit_inputs.mapped("code"))), 18)
        self._input(slip, "DVZ_FUEL", 125)
        slip.compute_sheet()
        totals = self._totals(slip)
        input_ids = slip.input_line_ids.ids
        for _iteration in range(3):
            slip.compute_sheet()
            self.assertEqual(self._totals(slip), totals)
            self.assertEqual(slip.input_line_ids.ids, input_ids)
        self.assertEqual(totals["DVZ_FUEL"], 625)

    def test_zero_inputs_work_without_configuring_quantity_divisors(self):
        rules = self.structure.rule_ids.filtered("dvz_benefit_rule")
        self.assertEqual(len(rules), 17)
        self.assertEqual(len(rules.mapped("input_ids")), 18)
        self.assertEqual(self.structure.parent_id, self.env.ref("om_hr_payroll.structure_base"))
        employer = rules.filtered(lambda rule: rule.code == "DVZ_PF_EMPLOYER")
        self.assertEqual(employer.category_id.code, "DVZ_COMP")
        self.assertFalse(employer.category_id.parent_id)
        slip = self._payslip(self._employee())
        slip.compute_sheet()
        totals = self._totals(slip)
        self.assertEqual(totals["NET"], 10000)
        self.assertFalse(any(code.startswith("DVZ_") for code in totals))

    def test_positive_quantity_requires_a_valid_salary_days_divisor(self):
        slip = self._payslip(self._employee(dvz_salary_days_divisor=0))
        self._input(slip, "DVZ_LEAVE_DAYS", 2)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            slip.compute_sheet()

    def test_negative_native_input_is_rejected(self):
        slip = self._payslip(self._employee())
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._input(slip, "DVZ_EX_GRATIA", -100)
            slip.compute_sheet()

    def test_input_from_another_employment_version_is_rejected(self):
        employee = self._employee()
        other = self._employee()
        slip = self._payslip(employee)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._input(slip, "DVZ_FUEL", 100, version=other.version_id)
            slip.compute_sheet()

    def test_duplicate_native_input_rows_are_summed_once(self):
        slip = self._payslip(self._employee())
        self._input(slip, "DVZ_FUEL", 70)
        self._input(slip, "DVZ_FUEL", 30, append=True)
        slip.compute_sheet()
        self.assertEqual(self._totals(slip)["DVZ_FUEL"], 100)
        self.assertEqual(self._totals(slip)["NET"], 10100)

