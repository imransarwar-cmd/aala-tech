"""Source-policy configuration and employee-scope integration tests."""
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestConfigurableLeavePolicy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        common = {"company_id": cls.company.id, "request_unit": "half_day",
            "leave_validation_type": "both", "allocation_validation_type": "hr",
            "include_public_holidays_in_duration": False, "time_type": "leave"}
        cls.annual_type = cls.env["hr.leave.type"].create({
            **common, "name": "Test Paid Policy Type", "requires_allocation": True, "unpaid": False})
        cls.unpaid_type = cls.env["hr.leave.type"].create({
            **common, "name": "Test Unpaid Policy Type", "requires_allocation": False, "unpaid": True})
        cls.employee = cls.env["hr.employee"].create({"name": "Policy Test Employee", "company_id": cls.company.id,
            "dvz_employment_status": "permanent", "dvz_joining_date": "2024-01-01", "dvz_paid_eligible_date": "2024-04-01"})

    def _policy(self, **changes):
        return self.env["dvz.leave.policy"].create({"name": "Test Source Policy", "company_id": self.company.id,
            "date_from": "2026-01-01", "date_to": "2026-12-31", "annual_leave_type_id": self.annual_type.id,
            "unpaid_leave_type_id": self.unpaid_type.id, "wfh_enabled": False, "exception_mode": "disabled", **changes})

    def _user(self, login, groups="base.group_user"):
        return new_test_user(self.env, login=login, groups=groups,
            company_id=self.company.id, company_ids=[Command.set(self.company.ids)])

    def test_policy_activation_is_explicit_including_defaults(self):
        policy = self._policy()
        with self.assertRaises(UserError):
            policy.write({"state": "active"})
        with self.assertRaises(UserError):
            self.env["dvz.leave.policy"].with_context(default_state="active").create({"name": "Invalid activation"})
        policy.action_activate()
        self.assertEqual(policy.state, "active")

    def test_annual_quantity_is_configurable_on_draft(self):
        policy = self._policy(annual_days=30)
        self.assertEqual(policy._compute_entitlement(self.employee, "2026-01-01", "2026-12-31", "2026-01-01"), 30)
        policy.write({"annual_days": 18})
        self.assertEqual(policy._compute_entitlement(self.employee, "2026-01-01", "2026-12-31", "2026-01-01"), 18)

    def test_active_rules_need_a_revision(self):
        policy = self._policy()
        policy.action_activate()
        with self.assertRaises(UserError):
            policy.write({"annual_days": 30})
        revision = self.env["dvz.leave.policy"].browse(policy.action_revision()["res_id"])
        self.assertEqual(revision.version, policy.version + 1)
        self.assertEqual(revision.state, "draft")
        revision.annual_days = 30
        self.assertEqual(policy.annual_days, 24)

    def test_used_draft_rules_cannot_be_rewritten(self):
        policy = self._policy()
        with patch.object(type(policy), "_has_usage", return_value=True):
            with self.assertRaises(UserError):
                policy.write({"rounding_step": 1})

    def test_activation_does_not_assign_any_employee(self):
        policy = self._policy()
        policy.action_activate()
        self.assertFalse(self.employee.dvz_leave_policy_id)
        self.assertFalse(self.env["dvz.leave.policy"]._get_for_employee(self.employee, "2026-02-01"))

    def test_only_the_explicit_assignment_is_resolved(self):
        first, second = self._policy(), self._policy(name="Another Employee Policy", annual_days=30)
        first.action_activate()
        second.action_activate()
        self.employee.dvz_leave_policy_id = second
        found = self.env["dvz.leave.policy"]._get_for_employee(self.employee, "2026-02-01")
        self.assertEqual(found, second)
        with self.assertRaises(UserError):
            self.env["dvz.leave.policy"]._get_for_employee(self.employee, "2027-01-01")

    def test_verified_confirmation_is_required(self):
        self.employee.dvz_paid_eligible_date = False
        self.assertFalse(self._policy()._employee_eligibility(self.employee, "2026-02-01")["eligible"])
        self.employee.dvz_probation_end_date = "2024-03-31"
        self.assertTrue(self._policy()._employee_eligibility(self.employee, "2026-02-01")["eligible"])

    def test_probation_status_never_receives_paid_eligibility(self):
        self.employee.dvz_employment_status = "probation"
        self.assertFalse(self._policy()._employee_eligibility(self.employee, "2026-02-01")["eligible"])

    def test_regular_user_cannot_change_eligibility(self):
        regular = self._user("dvz_policy_regular_test")
        with self.assertRaises(AccessError):
            self.employee.with_user(regular).write({"dvz_employment_status": "permanent"})

    def test_creation_defaults_cannot_bypass_employee_configuration_access(self):
        officer = self._user("dvz_policy_hr_officer", "hr.group_hr_user")
        with self.assertRaises(AccessError):
            self.env["hr.employee"].with_user(officer).with_context(default_dvz_employment_status="permanent").create({
                "name": "Unverified Configuration", "company_id": self.company.id})

    def test_explicit_hr_and_management_require_officer_access(self):
        regular = self._user("dvz_policy_unprivileged_approver")
        for values in ({"hr_user_ids": [Command.set(regular.ids)]},
                       {"management_user_ids": [Command.set(regular.ids)], "exception_mode": "all_three"}):
            policy = self._policy(**values)
            with self.assertRaisesRegex(UserError, "Officer"), self.cr.savepoint():
                policy.action_activate()

    def test_native_employee_hod_needs_no_officer_role(self):
        native = self._user("dvz_policy_native_hod")
        self.employee.leave_manager_id = native
        self.assertTrue(native.has_group("hr_holidays.group_hr_holidays_responsible"))
        self.assertFalse(native.has_group("hr_holidays.group_hr_holidays_user"))
        self.assertTrue(self._policy()._validate_approvers_for_employee(self.employee, ["hod"]))

    def test_missing_or_self_only_hod_is_rejected(self):
        self.employee.leave_manager_id = False
        policy = self._policy()
        with self.assertRaisesRegex(UserError, "No active"):
            policy._validate_approvers_for_employee(self.employee, ["hod"])
        person = self._user("dvz_policy_self_only")
        self.employee.write({"user_id": person.id, "leave_manager_id": person.id})
        with self.assertRaisesRegex(UserError, "self-approval"):
            policy._validate_approvers_for_employee(self.employee, ["hod"])

    def test_hod_and_hr_need_distinct_eligible_users(self):
        officer = self._user("dvz_policy_shared_approver", "hr_holidays.group_hr_holidays_user")
        self.employee.leave_manager_id = officer
        policy = self._policy(hr_user_ids=[Command.set(officer.ids)])
        with self.assertRaisesRegex(UserError, "two different"):
            policy._validate_approvers_for_employee(self.employee, ["hod", "hr"])
        second = self._user("dvz_policy_second_approver", "hr_holidays.group_hr_holidays_user")
        policy.hr_user_ids = [Command.set((officer | second).ids)]
        self.assertTrue(policy._validate_approvers_for_employee(self.employee, ["hod", "hr"]))

    def test_policy_dates_and_amounts_are_validated(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._policy(annual_days=-1)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._policy(date_to="2025-12-31")

