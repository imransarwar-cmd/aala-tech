"""Single-employee annual grant safety and wizard integration tests."""
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPolicyAllocations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        common = {"company_id": cls.company.id, "request_unit": "half_day",
            "leave_validation_type": "both", "allocation_validation_type": "hr",
            "include_public_holidays_in_duration": False, "time_type": "leave"}
        cls.leave_type = cls.env["hr.leave.type"].create({**common, "name": "Annual Allocation Test Type",
            "requires_allocation": True, "unpaid": False})
        cls.unpaid_type = cls.env["hr.leave.type"].create({**common, "name": "Unpaid Allocation Test Type",
            "requires_allocation": False, "unpaid": True})
        cls.employee = cls.env["hr.employee"].create({"name": "Annual Allocation Test Employee",
            "company_id": cls.company.id, "dvz_employment_status": "permanent",
            "dvz_joining_date": "2024-01-01", "dvz_paid_eligible_date": "2024-04-01"})

    def _policy(self, **changes):
        policy = self.env["dvz.leave.policy"].create({"name": "Annual Allocation Test Policy",
            "company_id": self.company.id, "date_from": "2026-01-01", "date_to": "2026-12-31",
            "annual_leave_type_id": self.leave_type.id, "unpaid_leave_type_id": self.unpaid_type.id,
            "wfh_enabled": False, "exception_mode": "disabled", **changes})
        policy.action_activate()
        self.employee.dvz_leave_policy_id = policy
        return policy

    def _wizard(self, policy, day="2026-01-01", **changes):
        return self.env["dvz.leave.allocation.wizard"].create({
            "policy_id": policy.id, "as_of_date": day, "employee_id": self.employee.id, **changes})

    def test_repeated_single_employee_generation_reuses_one_grant(self):
        wizard = self._wizard(self._policy())
        wizard.action_preview()
        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.line_ids.status, "create")
        self.assertEqual(wizard.line_ids.days, 24)
        wizard.action_generate()
        wizard.action_generate()
        grants = self.env["hr.leave.allocation"].search([
            ("employee_id", "=", self.employee.id), ("dvz_policy_id", "=", wizard.policy_id.id)])
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants.number_of_days, 24)
        self.assertEqual(grants.state, "confirm")
        self.assertEqual(grants.date_to.isoformat(), "2026-12-31")

    def test_later_calculation_date_reuses_same_annual_grant(self):
        policy = self._policy()
        first = policy._create_allocation_for_employee(self.employee, "2026-01-01")
        later = policy._create_allocation_for_employee(self.employee, "2026-07-01")
        self.assertEqual(first, later)
        self.assertEqual(first.number_of_days, 24)

    def test_direct_provenance_forgery_is_rejected(self):
        policy = self._policy()
        values = policy._allocation_values_for_employee(self.employee, "2026-01-01")["values"]
        with self.assertRaises(AccessError):
            self.env["hr.leave.allocation"].create(values)

    def test_context_provenance_forgery_is_rejected(self):
        policy = self._policy()
        values = policy._allocation_values_for_employee(self.employee, "2026-01-01")["values"]
        defaults = {"default_" + key: values.pop(key) for key in tuple(values) if key.startswith("dvz_")}
        with self.assertRaises(AccessError):
            self.env["hr.leave.allocation"].with_context(**defaults).create(values)

    def test_generation_ignores_client_workflow_defaults(self):
        policy = self._policy()
        values = policy._allocation_values_for_employee(self.employee, "2026-01-01")["values"]
        allocation = self.env["hr.leave.allocation"].with_context(default_state="validate",
            default_number_of_days_display=99, default_dvz_policy_version=99)._dvz_create_generated(values)
        self.assertEqual(allocation.state, "confirm")
        self.assertEqual(allocation.number_of_days, 24)
        self.assertEqual(allocation.dvz_policy_version, policy.version)

    def test_manual_overlap_blocks_generation(self):
        policy = self._policy()
        self.env["hr.leave.allocation"].create({"employee_id": self.employee.id,
            "holiday_status_id": self.leave_type.id, "number_of_days": 5,
            "date_from": "2026-01-01", "date_to": "2026-12-31"})
        wizard = self._wizard(policy)
        wizard.action_preview()
        self.assertEqual(wizard.line_ids.status, "error")
        with self.assertRaises(UserError):
            wizard.action_generate()
        self.assertFalse(self.env["hr.leave.allocation"].search([
            ("employee_id", "=", self.employee.id), ("dvz_policy_id", "=", policy.id)]))

    def test_new_paid_type_cannot_duplicate_an_existing_native_balance(self):
        policy = self._policy()
        existing_type = self.env["hr.leave.type"].create({"name": "Existing Native Paid Balance",
            "company_id": self.company.id, "requires_allocation": True, "request_unit": "day",
            "unpaid": False, "time_type": "leave", "allocation_validation_type": "hr"})
        self.env["hr.leave.allocation"].create({"employee_id": self.employee.id,
            "holiday_status_id": existing_type.id, "number_of_days": 12,
            "date_from": "2026-01-01", "date_to": "2026-12-31"})
        with self.assertRaisesRegex(UserError, "Existing paid allocations"):
            policy._create_allocation_for_employee(self.employee, "2026-01-01")

    def test_probation_receives_no_paid_grant(self):
        policy = self._policy()
        self.employee.write({"dvz_employment_status": "probation", "dvz_paid_eligible_date": False})
        wizard = self._wizard(policy)
        wizard.action_preview()
        self.assertEqual(wizard.line_ids.status, "skip")
        self.assertEqual(wizard.line_ids.days, 0)
        self.assertFalse(policy._create_allocation_for_employee(self.employee, "2026-01-01"))
        self.assertFalse(self.env["hr.leave.allocation"].search([
            ("employee_id", "=", self.employee.id), ("dvz_policy_id", "=", policy.id)]))

    def test_new_joiner_grant_starts_at_verified_eligibility(self):
        policy = self._policy()
        self.employee.write({"dvz_joining_date": "2026-04-01", "dvz_paid_eligible_date": "2026-07-01"})
        allocation = policy._create_allocation_for_employee(self.employee, "2026-07-01")
        self.assertEqual(allocation.number_of_days, 18)
        self.assertEqual(allocation.date_from.isoformat(), "2026-07-01")
        self.assertEqual(allocation.date_to.isoformat(), "2026-12-31")

    def test_explicit_assignment_is_required_and_never_filled_automatically(self):
        policy = self._policy()
        self.employee.dvz_leave_policy_id = False
        with self.assertRaises(UserError):
            policy._create_allocation_for_employee(self.employee, "2026-01-01")
        self.assertFalse(self.employee.dvz_leave_policy_id)

    def test_generation_affects_only_the_selected_employee(self):
        policy = self._policy()
        other = self.env["hr.employee"].create({"name": "Unselected Employee", "company_id": self.company.id,
            "dvz_employment_status": "permanent", "dvz_joining_date": "2024-01-01", "dvz_paid_eligible_date": "2024-04-01"})
        allocation = policy._create_allocation_for_employee(self.employee, "2026-01-01")
        self.assertEqual(allocation.employee_id, self.employee)
        self.assertFalse(other.dvz_leave_policy_id)
        self.assertFalse(self.env["hr.leave.allocation"].search([("employee_id", "=", other.id)]))
        with self.assertRaises(ValueError):
            policy._create_allocation_for_employee(self.employee | other, "2026-01-01")

    def test_generated_financial_identity_cannot_be_edited_or_copied(self):
        policy = self._policy()
        allocation = policy._create_allocation_for_employee(self.employee, "2026-01-01")
        with self.assertRaises(UserError):
            allocation.write({"number_of_days": 99})
        with self.assertRaises(AccessError):
            allocation.write({"dvz_policy_version": 99})
        with self.assertRaises(UserError):
            allocation.copy()

    def test_approval_is_an_explicit_native_action(self):
        policy = self._policy()
        allocation = policy._create_allocation_for_employee(self.employee, "2026-01-01", approve=False)
        self.assertEqual(allocation.state, "confirm")
        self.assertEqual(policy._create_allocation_for_employee(self.employee, "2026-01-01", approve=True), allocation)
        self.assertEqual(allocation.state, "validate")

    def test_closed_period_blocks_manual_and_generated_sources(self):
        policy = self._policy()
        Allocation = self.env["hr.leave.allocation"]
        values = policy._allocation_values_for_employee(self.employee, "2026-01-01")["values"]
        manual = {"employee_id": self.employee.id, "holiday_status_id": self.leave_type.id,
            "number_of_days": 5, "date_from": "2026-01-01", "date_to": "2026-12-31"}
        existing = Allocation.create(manual)
        following = Allocation.create({**manual, "date_from": "2027-01-01", "date_to": "2027-12-31"})
        settlement = self.env["dvz.leave.settlement"].create({"company_id": self.company.id, "policy_id": policy.id,
            "employee_id": self.employee.id, "period_start": "2026-01-01", "period_end": "2026-12-31"})
        # A private fixture isolates source-lock guards from settlement tests.
        settlement._internal_write({"state": "approved"})
        with self.assertRaises(UserError):
            Allocation.create(manual)
        with self.assertRaises(UserError):
            Allocation._dvz_create_generated(values)
        with self.assertRaises(UserError):
            existing.write({"number_of_days": 6})
        with self.assertRaises(UserError):
            existing.write({"state": "refuse"})
        with self.assertRaises(UserError):
            existing.unlink()
        with self.assertRaises(UserError):
            following.write({"date_from": "2026-12-01"})
        self.assertEqual(following.date_from.isoformat(), "2027-01-01")
        with self.assertRaises(UserError):
            Allocation.with_context(default_employee_id=self.employee.id,
                default_holiday_status_id=self.leave_type.id, default_date_from="2026-01-01",
                default_date_to="2026-12-31").create({"number_of_days": 1})

