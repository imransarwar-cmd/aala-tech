"""Automatic assignment never grants or invents an employee's paid eligibility."""

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestEmployeePolicyAssignment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.dvz_default_leave_policy_id = False
        cls.officer = new_test_user(cls.env, login="dvz_assignment_hr_officer", groups="hr.group_hr_user",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        cls.policy = cls._make_policy(cls.company)

    @classmethod
    def _make_policy(cls, company, **changes):
        Policy = cls.env["dvz.leave.policy"].with_company(company)
        policy = Policy.create({"name": "New Employee Policy", "company_id": company.id,
            "date_from": "2020-01-01", "wfh_enabled": False, "exception_mode": "disabled",
            "approval_mode": "none", "unpaid_approval_mode": "none", **changes})
        for kind, field in (("paid", "annual_leave_type_id"), ("unpaid", "unpaid_leave_type_id")):
            policy[field] = cls.env["hr.leave.type"].with_company(company).create({
                **policy._type_settings(kind), "name": "Assignment Test " + kind, "company_id": company.id})
        policy.action_activate()
        return policy

    def _employee(self, **changes):
        return self.env["hr.employee"].create({"name": "New Policy Employee", "company_id": self.company.id, **changes})

    def test_assignment_accepts_unknown_status_and_missing_dates_without_allocating(self):
        self.policy.action_use_for_new_employees()
        employee = self._employee()
        self.assertEqual(employee.dvz_leave_policy_id, self.policy)
        self.assertEqual(employee.dvz_employment_status, "unknown")
        self.assertFalse(employee.dvz_joining_date)
        self.assertFalse(employee.dvz_paid_eligible_date)
        self.assertFalse(employee.dvz_probation_end_date)
        self.assertFalse(self.policy._employee_eligibility(employee, "2027-01-01")["eligible"])
        self.assertFalse(self.env["hr.leave.allocation"].search_count([("employee_id", "=", employee.id)]))
        with self.assertRaisesRegex(UserError, "joining"), self.cr.savepoint():
            self.policy._allocation_values_for_employee(employee, "2027-01-01")

    def test_no_default_leaves_automatic_assignment_disabled(self):
        self.assertFalse(self.policy.is_employee_default)
        self.assertFalse(self._employee().dvz_leave_policy_id)

    def test_hr_officer_create_receives_default_without_configuration_permissions(self):
        self.policy.action_use_for_new_employees()
        employee = self.env["hr.employee"].with_user(self.officer).create({
            "name": "Officer Created Employee", "company_id": self.company.id})
        self.assertEqual(employee.dvz_leave_policy_id, self.policy)
        with self.assertRaises(AccessError), self.cr.savepoint():
            employee.write({"dvz_employment_status": "permanent"})

    def test_native_employee_create_access_is_not_elevated(self):
        self.policy.action_use_for_new_employees()
        regular = new_test_user(self.env, login="dvz_assignment_regular", groups="base.group_user",
            company_id=self.company.id, company_ids=[Command.set(self.company.ids)])
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env["hr.employee"].with_user(regular).create({
                "name": "Unauthorized Employee", "company_id": self.company.id})

    def test_explicit_administrator_policy_is_preserved_but_blank_uses_default(self):
        self.policy.action_use_for_new_employees()
        other = self._make_policy(self.company, name="Explicit Employee Policy")
        self.assertEqual(self._employee(dvz_leave_policy_id=other.id).dvz_leave_policy_id, other)
        self.assertEqual(self._employee(dvz_leave_policy_id=False).dvz_leave_policy_id, self.policy)
        employee = self.env["hr.employee"].with_context(default_dvz_leave_policy_id=other.id).create({
            "name": "Explicit Context Policy", "company_id": self.company.id})
        self.assertEqual(employee.dvz_leave_policy_id, other)

    def test_protected_values_and_context_cannot_bypass_configuration_access(self):
        self.policy.action_use_for_new_employees()
        Employee = self.env["hr.employee"].with_user(self.officer)
        for context, values in (({"default_dvz_leave_policy_id": self.policy.id}, {}),
                                ({"default_dvz_employment_status": "permanent"}, {}),
                                ({}, {"dvz_leave_policy_id": False}),
                                ({}, {"dvz_paid_eligible_date": "2026-01-01"})):
            with self.assertRaises(AccessError), self.cr.savepoint():
                Employee.with_context(**context).create({"name": "Unverified Defaults", **values})

    def test_multi_company_batch_uses_each_employee_company(self):
        second_company = self.env["res.company"].create({"name": "Policy Assignment Second Company"})
        second_policy = self._make_policy(second_company)
        companies = self.company | second_company
        self.policy.action_use_for_new_employees()
        second_policy.with_context(allowed_company_ids=companies.ids).action_use_for_new_employees()
        employees = self.env["hr.employee"].with_context(
            allowed_company_ids=companies.ids, default_company_id=second_company.id).create([
                {"name": "First Company Employee", "company_id": self.company.id},
                {"name": "Context Company Employee"},
                {"name": "Explicit Second Employee", "company_id": second_company.id},
            ])
        self.assertEqual(employees[0].dvz_leave_policy_id, self.policy)
        self.assertEqual(employees[1].company_id, second_company)
        self.assertEqual(employees[1].dvz_leave_policy_id, second_policy)
        self.assertEqual(employees[2].dvz_leave_policy_id, second_policy)

    def test_employee_copy_resets_personal_eligibility_and_approver(self):
        self.policy.action_use_for_new_employees()
        original = self._employee(dvz_employment_status="permanent", dvz_joining_date="2024-01-01",
            dvz_paid_eligible_date="2024-04-01", dvz_probation_end_date="2024-03-31",
            leave_manager_id=self.officer.id)
        replacement = self._make_policy(self.company, name="Default for New Copies")
        replacement.action_use_for_new_employees()
        copied = original.copy({"name": "Copied Employee"})
        self.assertEqual(copied.dvz_leave_policy_id, replacement)
        self.assertEqual(copied.dvz_employment_status, "unknown")
        self.assertFalse(copied.dvz_joining_date or copied.dvz_probation_end_date or copied.dvz_paid_eligible_date)
        self.assertFalse(copied.leave_manager_id)
        self.assertEqual(original.dvz_leave_policy_id, self.policy)

    def test_switching_default_changes_only_future_employees(self):
        unassigned = self._employee(name="Existing Unassigned Employee")
        self.policy.action_use_for_new_employees()
        assigned = self._employee(name="Existing Assigned Employee")
        replacement = self._make_policy(self.company, name="Replacement New Employee Policy")
        replacement.action_use_for_new_employees()
        self.assertFalse(unassigned.dvz_leave_policy_id)
        self.assertEqual(assigned.dvz_leave_policy_id, self.policy)
        self.assertEqual(self._employee().dvz_leave_policy_id, replacement)
        self.assertFalse(self.policy.is_employee_default)
        self.assertTrue(replacement.is_employee_default)

    def test_stop_does_not_clear_existing_assignments_or_another_default(self):
        self.policy.action_use_for_new_employees()
        employee = self._employee()
        replacement = self._make_policy(self.company, name="Another Default")
        replacement.action_use_for_new_employees()
        self.policy.action_stop_automatic_assignment()
        self.assertEqual(self.company.dvz_default_leave_policy_id, replacement)
        replacement.action_stop_automatic_assignment()
        self.assertEqual(employee.dvz_leave_policy_id, self.policy)
        self.assertFalse(self._employee().dvz_leave_policy_id)

    def test_current_default_cannot_be_retired_or_archived_until_replaced(self):
        self.policy.action_use_for_new_employees()
        with self.assertRaisesRegex(UserError, "automatic assignment"), self.cr.savepoint():
            self.policy.action_retire()
        with self.assertRaisesRegex(UserError, "automatic assignment"), self.cr.savepoint():
            self.policy.write({"active": False})
        replacement = self._make_policy(self.company, name="Replacement Default")
        replacement.action_use_for_new_employees()
        self.policy.action_retire()
        self.assertEqual(self.policy.state, "retired")

    def test_default_selection_requires_admin_and_active_same_company_policy(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.policy.with_user(self.officer).action_use_for_new_employees()
        draft = self.policy.copy({"name": "Draft Cannot Be Default"})
        with self.assertRaises(UserError), self.cr.savepoint():
            draft.action_use_for_new_employees()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.company.write({"dvz_default_leave_policy_id": draft.id})
        second_company = self.env["res.company"].create({"name": "Wrong Default Company"})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            second_company.write({"dvz_default_leave_policy_id": self.policy.id})

    def test_stale_inactive_default_fails_closed(self):
        self.policy.action_use_for_new_employees()
        # Simulate a stale configuration left by external SQL/older code; no
        # ordinary action may create this state in the current version.
        self.env.cr.execute("UPDATE dvz_leave_policy SET state = 'retired' WHERE id = %s", [self.policy.id])
        self.policy.invalidate_recordset(["state"])
        with self.assertRaisesRegex(UserError, "policy for new employees is unavailable"), self.cr.savepoint():
            self._employee()

    def test_assignment_does_not_require_current_effective_dates(self):
        for start, end, request_day in (("2999-01-01", False, "2027-01-01"),
                                        ("2000-01-01", "2000-12-31", "2027-01-01")):
            policy = self._make_policy(self.company, date_from=start, date_to=end)
            policy.action_use_for_new_employees()
            employee = self._employee()
            self.assertEqual(employee.dvz_leave_policy_id, policy)
            with self.assertRaisesRegex(UserError, "not active for this date"):
                policy._get_for_employee(employee, request_day)
