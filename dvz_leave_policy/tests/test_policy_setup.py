"""One-existing-employee setup and source-only preset regressions."""

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestSourcePolicySetup(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.hod = new_test_user(cls.env, login="dvz_one_setup_hod", groups="hr_holidays.group_hr_holidays_manager",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        cls.hr = new_test_user(cls.env, login="dvz_one_setup_hr", groups="hr_holidays.group_hr_holidays_manager",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        cls.management = new_test_user(cls.env, login="dvz_one_setup_management", groups="hr_holidays.group_hr_holidays_manager",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        cls.employee = cls.env["hr.employee"].create({"name": "Selected Setup Test Employee",
            "company_id": cls.company.id, "dvz_employment_status": "permanent",
            "dvz_joining_date": "2024-01-01", "dvz_paid_eligible_date": "2024-04-01"})
        cls.other_employee = cls.env["hr.employee"].create({"name": "Unselected Setup Test Employee",
            "company_id": cls.company.id, "dvz_employment_status": "permanent",
            "dvz_joining_date": "2024-01-01", "dvz_paid_eligible_date": "2024-04-01"})

    def _wizard(self, **changes):
        return self.env["dvz.policy.setup.wizard"].create({
            "company_id": self.company.id, "employee_id": self.employee.id,
            "policy_id": False, "name": "Source Setup Test Policy", "date_from": "2027-01-01", "date_to": False,
            "employment_status": "permanent", "joining_date": "2024-01-01", "paid_eligible_date": "2024-04-01",
            "hod_user_id": self.hod.id, "hr_user_id": self.hr.id, "management_user_id": self.management.id,
            "annual_leave_type_id": False, "unpaid_leave_type_id": False, "wfh_leave_type_id": False,
            "reviewed": True, "as_of_date": "2027-01-01", **changes,
        })

    def test_source_preset_is_unassigned_draft_with_three_types(self):
        policy = self.env.ref("dvz_leave_policy.policy_document_preset")
        self.assertEqual(policy.name, "Leave and Absence Policy")
        self.assertEqual(policy.state, "draft")
        self.assertFalse(policy.configuration_reviewed)
        self.assertEqual(policy.source_revision_date.isoformat(), "2025-03-10")
        self.assertEqual(policy.annual_days, 24)
        self.assertEqual(policy.half_day_notice_days, 1)
        self.assertEqual(policy.half_day_return_action, "full_day")
        self.assertEqual(policy.exception_mode, "all_three")
        self.assertTrue(policy.wfh_availability_required and policy.wfh_communication_required)
        self.assertEqual(len(policy.annual_leave_type_id | policy.unpaid_leave_type_id | policy.wfh_leave_type_id), 3)
        self.assertFalse(policy._has_usage())
        self.assertFalse(self.env["hr.employee"].search_count([("dvz_leave_policy_id", "=", policy.id)]))
        for removed in ("is_default", "year_start_month", "allocation_frequency", "auto_allocation", "carry_limit", "hour_settlement_mode"):
            self.assertNotIn(removed, policy._fields)

    def test_apply_changes_exactly_the_selected_existing_employee(self):
        employee_count = self.env["hr.employee"].search_count([])
        wizard = self._wizard()
        action = wizard.action_apply_employee()
        policy = wizard.result_policy_id
        self.assertTrue(wizard.setup_applied)
        self.assertEqual(action["res_model"], "dvz.policy.setup.wizard")
        self.assertEqual(action["res_id"], wizard.id)
        self.assertEqual(policy.state, "active")
        self.assertEqual(self.employee.dvz_leave_policy_id, policy)
        self.assertEqual(self.employee.leave_manager_id, self.hod)
        self.assertEqual(policy.hr_user_ids, self.hr)
        self.assertEqual(policy.management_user_ids, self.management)
        self.assertFalse(self.other_employee.dvz_leave_policy_id)
        self.assertEqual(self.env["hr.employee"].search_count([]), employee_count)
        self.assertFalse(self.env["hr.leave.allocation"].search_count([("dvz_policy_id", "=", policy.id)]))

    def test_save_draft_does_not_assign_employee(self):
        wizard = self._wizard(reviewed=False)
        wizard.action_create_draft()
        self.assertEqual(wizard.result_policy_id.state, "draft")
        self.assertFalse(wizard.setup_applied)
        self.assertFalse(self.employee.dvz_leave_policy_id)
        self.assertFalse(self.other_employee.dvz_leave_policy_id)

    def test_review_is_required_before_any_application(self):
        wizard = self._wizard(reviewed=False)
        count = self.env["dvz.leave.policy"].search_count([])
        with self.assertRaisesRegex(UserError, "Verify"), self.cr.savepoint():
            wizard.action_apply_employee()
        self.assertFalse(wizard.result_policy_id)
        self.assertFalse(self.employee.dvz_leave_policy_id)
        self.assertEqual(self.env["dvz.leave.policy"].search_count([]), count)

    def test_repeated_apply_and_generation_reuse_one_employee_grant(self):
        wizard = self._wizard()
        wizard.action_apply_employee()
        policy = wizard.result_policy_id
        wizard.action_apply_employee()
        self.assertEqual(wizard.result_policy_id, policy)
        wizard.action_preview_allocation()
        self.assertEqual(wizard.allocation_status, "create")
        self.assertEqual(wizard.allocation_days, 24)
        wizard.action_generate_allocation()
        allocation = wizard.allocation_id
        wizard.action_generate_allocation()
        self.assertEqual(wizard.allocation_id, allocation)
        self.assertEqual(allocation.employee_id, self.employee)
        self.assertEqual(allocation.state, "confirm")
        self.assertEqual(self.env["hr.leave.allocation"].search_count([("dvz_policy_id", "=", policy.id)]), 1)
        self.assertFalse(self.env["hr.leave.allocation"].search_count([("employee_id", "=", self.other_employee.id)]))

    def test_probation_needs_no_fabricated_confirmation_date(self):
        wizard = self._wizard(employment_status="probation", paid_eligible_date=False)
        wizard.action_apply_employee()
        self.assertEqual(self.employee.dvz_employment_status, "probation")
        self.assertFalse(self.employee.dvz_paid_eligible_date)
        wizard.action_preview_allocation()
        self.assertEqual(wizard.allocation_status, "skip")
        self.assertEqual(wizard.allocation_days, 0)
        wizard.action_generate_allocation()
        self.assertFalse(wizard.allocation_id)

    def test_permanent_employee_requires_verified_paid_date(self):
        wizard = self._wizard(paid_eligible_date=False)
        with self.assertRaisesRegex(UserError, "verified"), self.cr.savepoint():
            wizard.action_apply_employee()
        self.assertFalse(self.employee.dvz_leave_policy_id)

    def test_compatible_active_policy_can_be_assigned_without_mutation(self):
        first = self._wizard()
        first.action_apply_employee()
        policy = first.result_policy_id
        before = (policy.name, policy.date_from, policy.date_to, policy.annual_days,
                  policy.hr_user_ids.ids, policy.management_user_ids.ids, policy.annual_leave_type_id.id)
        second = self._wizard(employee_id=self.other_employee.id, policy_id=policy.id,
            name="Must Not Replace Active Policy", date_from="2028-01-01")
        second.action_apply_employee()
        self.assertEqual(self.other_employee.dvz_leave_policy_id, policy)
        self.assertEqual(before, (policy.name, policy.date_from, policy.date_to, policy.annual_days,
            policy.hr_user_ids.ids, policy.management_user_ids.ids, policy.annual_leave_type_id.id))

    def test_other_paid_manual_balance_blocks_new_type_grant(self):
        leave_type = self.env["hr.leave.type"].create({"name": "Existing Native Paid Balance",
            "company_id": self.company.id, "requires_allocation": True, "request_unit": "half_day",
            "leave_validation_type": "both", "allocation_validation_type": "hr"})
        existing = self.env["hr.leave.allocation"].create({"employee_id": self.employee.id,
            "holiday_status_id": leave_type.id, "number_of_days": 7,
            "date_from": "2027-01-01", "date_to": "2027-12-31"})
        wizard = self._wizard()
        wizard.action_apply_employee()
        self.assertNotEqual(wizard.result_policy_id.annual_leave_type_id, leave_type)
        wizard.action_preview_allocation()
        self.assertEqual(wizard.allocation_status, "error")
        with self.assertRaises(UserError), self.cr.savepoint():
            wizard.action_generate_allocation()
        self.assertEqual(existing.number_of_days, 7)
        self.assertFalse(self.env["hr.leave.allocation"].search_count([("dvz_policy_id", "=", wizard.result_policy_id.id)]))

    def test_changing_policy_after_draft_clears_prepared_result(self):
        wizard = self._wizard()
        wizard.action_create_draft()
        original = wizard.result_policy_id
        replacement = original.copy({"name": "Selected Replacement Draft"})
        wizard.write({"policy_id": replacement.id})
        self.assertFalse(wizard.result_policy_id)
        wizard.action_apply_employee()
        self.assertEqual(wizard.result_policy_id, replacement)
        self.assertEqual(self.employee.dvz_leave_policy_id, replacement)
        self.assertEqual(original.state, "draft")

    def test_employee_form_opens_setup_for_that_employee(self):
        action = self.employee.action_dvz_open_policy_setup()
        self.assertEqual(action["context"]["default_employee_id"], self.employee.id)
        self.assertEqual(action["res_model"], "dvz.policy.setup.wizard")

    def test_setup_results_cannot_be_forged(self):
        regular = new_test_user(self.env, login="dvz_one_setup_regular", groups="base.group_user",
            company_id=self.company.id, company_ids=[Command.set(self.company.ids)])
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env["dvz.policy.setup.wizard"].with_user(regular).create({"company_id": self.company.id})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env["dvz.policy.setup.wizard"].with_context(default_setup_applied=True).create({"company_id": self.company.id})
        wizard = self._wizard()
        with self.assertRaises(AccessError), self.cr.savepoint():
            wizard.write({"setup_applied": True})
