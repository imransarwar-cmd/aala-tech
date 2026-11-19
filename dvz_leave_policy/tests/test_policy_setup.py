"""One-existing-employee setup and source-only preset regressions."""

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, tagged
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

    def _wizard(self, user=None, **changes):
        Wizard = self.env["dvz.policy.setup.wizard"]
        if user:
            Wizard = Wizard.with_user(user)
        return Wizard.create({
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

    def test_permanent_employee_can_be_assigned_before_paid_date_is_known(self):
        wizard = self._wizard(paid_eligible_date=False, probation_end_date=False)
        wizard.action_apply_employee()
        self.assertTrue(wizard.setup_applied)
        policy = wizard.result_policy_id
        self.assertEqual(self.employee.dvz_leave_policy_id, policy)
        self.assertFalse(policy._employee_eligibility(self.employee, "2027-01-01")["eligible"])
        wizard.action_preview_allocation()
        self.assertEqual(wizard.allocation_status, "error")
        self.assertEqual(wizard.allocation_days, 0)
        with self.assertRaisesRegex(UserError, "first paid eligibility date"), self.cr.savepoint():
            wizard.action_generate_allocation()
        self.assertFalse(self.env["hr.leave.allocation"].search_count([("dvz_policy_id", "=", policy.id)]))
        request = self.env["hr.leave"].new({"employee_id": self.employee.id,
            "holiday_status_id": policy.annual_leave_type_id.id,
            "dvz_policy_id": policy.id, "request_date_from": "2027-01-04",
            "request_date_to": "2027-01-04"})
        with self.assertRaisesRegex(ValidationError, "Paid leave is not available"):
            request._dvz_validate_policy()

    def test_assignment_does_not_require_joining_or_probation_dates(self):
        for status in ("unknown", "probation", "temporary", "permanent"):
            with self.subTest(status=status):
                wizard = self._wizard(employment_status=status, joining_date=False,
                    paid_eligible_date=False, probation_end_date=False)
                wizard.action_apply_employee()
                self.assertTrue(wizard.setup_applied)
                self.assertEqual(self.employee.dvz_leave_policy_id, wizard.result_policy_id)
                self.assertEqual(self.employee.dvz_employment_status, status)
                self.assertFalse(self.employee.dvz_joining_date)
                wizard.action_preview_allocation()
                self.assertEqual(wizard.allocation_status, "error")
                self.assertEqual(wizard.allocation_days, 0)
                with self.assertRaisesRegex(UserError, "joining date"), self.cr.savepoint():
                    wizard.action_generate_allocation()
                self.assertFalse(wizard.allocation_id)

    def test_draft_does_not_require_employee_eligibility(self):
        wizard = self._wizard(employment_status="unknown", joining_date=False,
            paid_eligible_date=False, probation_end_date=False, reviewed=False)
        wizard.action_create_draft()
        self.assertEqual(wizard.result_policy_id.state, "draft")
        self.assertFalse(self.employee.dvz_leave_policy_id)

    def test_known_dates_must_still_follow_joining(self):
        for changes in ({"paid_eligible_date": "2023-12-31"},
                        {"probation_end_date": "2023-12-31"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError), self.cr.savepoint():
                self._wizard(**changes)

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
        self.assertFalse(wizard.reviewed)
        wizard.reviewed = True
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

    def test_auto_check_report_cannot_be_supplied_by_client(self):
        for name, value in (("auto_check_notes", "Forged verification"),
                            ("auto_paid_date", "2024-04-01"),
                            ("auto_checked_employee_id", self.employee.id)):
            with self.subTest(field=name):
                with self.assertRaises(AccessError), self.cr.savepoint():
                    self._wizard(**{name: value})
                with self.assertRaises(AccessError), self.cr.savepoint():
                    self.env["dvz.policy.setup.wizard"].with_context(**{"default_" + name: value}).create({})
                wizard = self._wizard()
                with self.assertRaises(AccessError), self.cr.savepoint():
                    wizard.write({name: value})
        # Normal unsaved form defaults contain false readonly fields.
        wizard = self._wizard(auto_check_notes=False, auto_paid_date=False,
            auto_checked_employee_id=False)
        self.assertFalse(wizard.auto_check_notes)

    def test_auto_check_uses_native_odoo19_probation_end(self):
        self.employee.write({"contract_date_start": "2024-01-01", "trial_date_end": "2024-03-31",
            "dvz_probation_end_date": False, "dvz_paid_eligible_date": False})
        wizard = self._wizard(paid_eligible_date=False)
        wizard.action_auto_check_employee()
        self.assertEqual(wizard.auto_contract_start, fields.Date.to_date("2024-01-01"))
        self.assertEqual(wizard.auto_probation_end, fields.Date.to_date("2024-03-31"))
        self.assertEqual(wizard.probation_end_date, fields.Date.to_date("2024-03-31"))
        self.assertEqual(wizard.paid_eligible_date, fields.Date.to_date("2024-04-01"))
        self.assertFalse(self.employee.dvz_probation_end_date)
        self.assertFalse(self.employee.dvz_paid_eligible_date)
        self.assertFalse(wizard.reviewed)

    def test_auto_check_without_hr_date_access_remains_available(self):
        self.employee.write({"contract_date_start": "2024-01-01", "trial_date_end": "2024-03-31",
            "dvz_probation_end_date": False, "dvz_paid_eligible_date": False})
        self.assertFalse(self.hr.has_group("hr.group_hr_manager"))
        wizard = self._wizard(user=self.hr, paid_eligible_date=False)
        wizard.action_auto_check_employee()
        self.assertFalse(wizard.auto_contract_start)
        self.assertFalse(wizard.auto_probation_end)
        self.assertFalse(wizard.probation_end_date)
        self.assertIn("require HR access", wizard.auto_check_notes)

    def test_auto_check_does_not_invent_joining_or_permanent_status(self):
        self.employee.write({"dvz_joining_date": False, "dvz_employment_status": "unknown",
            "dvz_probation_end_date": False, "dvz_paid_eligible_date": False,
            "contract_date_start": "2024-01-01", "trial_date_end": "2024-03-31"})
        wizard = self._wizard()
        wizard.action_auto_check_employee()
        self.assertFalse(wizard.joining_date)
        self.assertEqual(wizard.employment_status, "unknown")
        self.assertFalse(wizard.paid_eligible_date)
        self.assertEqual(wizard.auto_paid_date, fields.Date.to_date("2024-04-01"))

    def test_rechecking_clears_stale_eligibility_candidates(self):
        wizard = self._wizard()
        wizard.action_auto_check_employee()
        self.assertEqual(wizard.paid_eligible_date, self.employee.dvz_paid_eligible_date)
        self.employee.write({"dvz_joining_date": False, "dvz_employment_status": "unknown",
            "dvz_paid_eligible_date": False, "dvz_probation_end_date": False,
            "trial_date_end": False, "contract_date_start": False, "leave_manager_id": False})
        wizard.action_auto_check_employee()
        self.assertFalse(wizard.joining_date)
        self.assertFalse(wizard.paid_eligible_date)
        self.assertFalse(wizard.probation_end_date)
        self.assertFalse(wizard.hod_user_id)
        self.assertFalse(wizard.hr_user_id)
        self.assertFalse(wizard.management_user_id)
        self.assertEqual(wizard.employment_status, "unknown")

    def test_changed_employee_clears_check_and_old_employee_dates(self):
        wizard = self._wizard()
        wizard.action_auto_check_employee()
        self.other_employee.write({"dvz_joining_date": False, "dvz_employment_status": "unknown",
            "dvz_paid_eligible_date": False, "dvz_probation_end_date": False})
        wizard.write({"employee_id": self.other_employee.id})
        self.assertFalse(wizard.auto_checked_employee_id)
        self.assertFalse(wizard.auto_check_notes)
        self.assertFalse(wizard.joining_date)
        self.assertFalse(wizard.paid_eligible_date)
        self.assertEqual(wizard.employment_status, "unknown")
        self.assertFalse(wizard.reviewed)

    def test_form_can_change_employee_after_auto_check(self):
        wizard = self._wizard()
        wizard.action_auto_check_employee()
        with Form(wizard) as form:
            form.employee_id = self.other_employee
        self.assertEqual(wizard.employee_id, self.other_employee)
        self.assertFalse(wizard.auto_checked_employee_id)
        self.assertFalse(wizard.auto_check_notes)

    def test_renewed_review_in_same_policy_change_is_respected(self):
        wizard = self._wizard()
        wizard.action_create_draft()
        replacement = wizard.result_policy_id.copy({"name": "Reviewed Replacement Draft"})
        wizard.write({"policy_id": replacement.id, "reviewed": True})
        self.assertTrue(wizard.reviewed)
        wizard.action_apply_employee()
        self.assertEqual(self.employee.dvz_leave_policy_id, replacement)

    def test_auto_check_retains_verified_probation_when_native_date_conflicts(self):
        self.employee.write({"dvz_probation_end_date": "2024-04-30",
            "dvz_paid_eligible_date": False, "trial_date_end": "2024-03-31"})
        wizard = self._wizard(paid_eligible_date=False)
        wizard.action_auto_check_employee()
        self.assertEqual(wizard.auto_probation_end, fields.Date.to_date("2024-03-31"))
        self.assertEqual(wizard.probation_end_date, fields.Date.to_date("2024-04-30"))
        self.assertEqual(wizard.paid_eligible_date, fields.Date.to_date("2024-05-01"))
        self.assertIn("CONFLICT", wizard.auto_check_notes)

    def test_applied_setup_cannot_be_auto_checked_again(self):
        wizard = self._wizard()
        wizard.action_apply_employee()
        with self.assertRaisesRegex(UserError, "has been applied"), self.cr.savepoint():
            wizard.action_auto_check_employee()
        self.assertTrue(wizard.setup_applied)
        self.assertEqual(self.employee.dvz_leave_policy_id, wizard.result_policy_id)
