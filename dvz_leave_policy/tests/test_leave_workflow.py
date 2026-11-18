"""Integration tests for server-enforced policy approval and RPC guard paths."""
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestLeavePolicyWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.hod = new_test_user(cls.env, login="dvz_test_hod", groups="hr_holidays.group_hr_holidays_manager",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        cls.hr = new_test_user(cls.env, login="dvz_test_hr", groups="hr_holidays.group_hr_holidays_manager",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        cls.management = new_test_user(cls.env, login="dvz_test_management", groups="hr_holidays.group_hr_holidays_manager",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        cls.staff = new_test_user(cls.env, login="dvz_test_staff", groups="base.group_user",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        for user in (cls.hod, cls.hr, cls.management):
            cls.env["hr.employee"].create({"name": user.name, "user_id": user.id, "company_id": cls.company.id})
        today = fields.Date.today()
        cls.request_day = today + timedelta(days=14)
        while cls.request_day.weekday() != 0:
            cls.request_day += timedelta(days=1)

    def _prepare(self, **policy_changes):
        policy = self.env["dvz.leave.policy"].create({
            "name": "Workflow Test Policy", "company_id": self.company.id,
            "date_from": "2020-01-01", "wfh_enabled": False, "exception_mode": "disabled",
            "hr_user_ids": [Command.set(self.hr.ids)],
            "management_user_ids": [Command.set(self.management.ids)],
            "approval_mode": "both",
            "full_day_notice_days": 0, "require_prior_approval": True,
            **policy_changes,
        })
        paid = self.env["hr.leave.type"].create({
            **policy._type_settings("paid"), "name": "Workflow Paid Type", "company_id": self.company.id,
            "create_calendar_meeting": False,
        })
        unpaid = self.env["hr.leave.type"].create({
            **policy._type_settings("unpaid"), "name": "Workflow Unpaid Type", "company_id": self.company.id,
            "create_calendar_meeting": False,
        })
        policy.write({"annual_leave_type_id": paid.id, "unpaid_leave_type_id": unpaid.id})
        policy.action_activate()
        employee = self.env["hr.employee"].create({
            "name": "Workflow Test Staff", "company_id": self.company.id, "user_id": self.staff.id,
            "leave_manager_id": self.hod.id, "dvz_leave_policy_id": policy.id,
            "dvz_employment_status": "permanent", "dvz_joining_date": "2020-01-01",
            "dvz_paid_eligible_date": "2020-04-01", "resource_calendar_id": self.company.resource_calendar_id.id,
        })
        start, end = policy._get_period(self.request_day)
        allocation = self.env["hr.leave.allocation"].create({
            "name": "Workflow Test Allocation", "employee_id": employee.id,
            "holiday_status_id": paid.id, "allocation_type": "regular",
            "date_from": start, "date_to": end, "number_of_days": policy.annual_days,
        })
        allocation.action_approve()
        return policy, employee, paid, unpaid

    def _values(self, employee, leave_type, **changes):
        return {"name": "Policy Workflow Test", "employee_id": employee.id,
            "holiday_status_id": leave_type.id, "request_date_from": self.request_day,
            "request_date_to": self.request_day, "request_date_from_period": "am",
            "request_date_to_period": "pm", **changes}

    def test_hr_cannot_skip_department_even_with_check_state_false(self):
        policy, employee, paid, _ = self._prepare()
        leave = self.env["hr.leave"].create(self._values(employee, paid))
        self.assertEqual(leave.dvz_policy_id, policy)
        for skip_check in (False, True):
            with self.assertRaises(AccessError), self.cr.savepoint():
                leave.with_user(self.hr).action_approve(check_state=not skip_check)
        leave.with_user(self.hod).action_dvz_hod_approve()
        self.assertEqual(leave.state, "validate1")
        self.assertEqual(leave.dvz_hod_approved_by, self.hod)
        leave.with_user(self.hr).action_dvz_hr_approve()
        self.assertEqual(leave.state, "validate")
        self.assertEqual(leave.dvz_hr_approved_by, self.hr)

    def test_direct_state_write_and_forged_internal_context_are_blocked(self):
        _, employee, paid, _ = self._prepare()
        leave = self.env["hr.leave"].create(self._values(employee, paid))
        for values in ({"state": "validate"}, {"state": "validate1"}):
            with self.assertRaises(AccessError), self.cr.savepoint():
                leave.with_user(self.hr).with_context(_dvz_policy_internal=True).write(values)
        self.assertEqual(leave.state, "confirm")

    def test_distinct_approvers_is_enforced(self):
        _, employee, paid, _ = self._prepare(hr_user_ids=[Command.set((self.hod | self.hr).ids)])
        leave = self.env["hr.leave"].create(self._values(employee, paid))
        leave.with_user(self.hod).action_dvz_hod_approve()
        with self.assertRaises(AccessError), self.cr.savepoint():
            leave.with_user(self.hod).action_dvz_hr_approve()
        leave.with_user(self.hr).action_dvz_hr_approve()
        self.assertEqual(leave.state, "validate")

    def test_api_cannot_supply_approval_proof_or_kind(self):
        _, employee, paid, _ = self._prepare()
        leave = self.env["hr.leave"].create(self._values(employee, paid))
        for values in ({"dvz_hod_approved_by": self.hod.id}, {"dvz_kind": "unpaid"}):
            with self.assertRaises(AccessError), self.cr.savepoint():
                leave.with_user(self.hr).write(values)
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env["hr.leave"].create(self._values(employee, paid, dvz_hr_approved_by=self.hr.id))

    def test_rpc_default_context_cannot_inject_approval_evidence(self):
        _, employee, paid, _ = self._prepare()
        request = self.env["hr.leave"].with_context(
            default_dvz_hod_approved_by=self.hod.id, default_dvz_hr_approved_by=self.hr.id,
            default_dvz_kind="unpaid")
        # Either reject supplied audit defaults or remove them before native defaulting.
        try:
            with self.cr.savepoint():
                leave = request.create(self._values(employee, paid))
                self.assertFalse(leave.dvz_hod_approved_by)
                self.assertFalse(leave.dvz_hr_approved_by)
                self.assertEqual(leave.dvz_kind, "paid")
                self.assertEqual(leave.state, "confirm")
        except AccessError:
            pass

    def test_exception_requires_management_before_final_validation(self):
        _, employee, paid, _ = self._prepare(exception_mode="all_three")
        leave = self.env["hr.leave"].create(self._values(employee, paid,
            dvz_exception_requested=True, dvz_exception_reason="Documented exceptional request."))
        leave.with_user(self.hod).action_dvz_hod_approve()
        leave.with_user(self.hr).action_dvz_hr_approve()
        self.assertEqual(leave.state, "validate1")
        self.assertEqual(leave.dvz_hod_approved_by, self.hod)
        self.assertEqual(leave.dvz_hr_approved_by, self.hr)
        self.assertFalse(leave.dvz_management_approved_by)
        self.assertFalse(self.env["resource.calendar.leaves"].search_count([("holiday_id", "=", leave.id)]))
        leave.with_user(self.management).action_dvz_management_approve()
        self.assertEqual(leave.state, "validate")
        self.assertEqual(leave.dvz_management_approved_by, self.management)

    def test_refusal_preserves_native_resource_cleanup(self):
        _, employee, paid, _ = self._prepare()
        leave = self.env["hr.leave"].create(self._values(employee, paid))
        leave.with_user(self.hod).action_dvz_hod_approve()
        leave.with_user(self.hr).action_dvz_hr_approve()
        resource_leaves = self.env["resource.calendar.leaves"].search([("holiday_id", "=", leave.id)])
        self.assertTrue(resource_leaves)
        leave.with_user(self.hr).action_refuse()
        self.assertEqual(leave.state, "refuse")
        self.assertFalse(resource_leaves.exists())

    def test_afternoon_half_day_cannot_use_failed_return_conversion(self):
        _, employee, paid, _ = self._prepare(half_day_return_action="full_day")
        leave = self.env["hr.leave"].create(self._values(employee, paid,
            request_date_from_period="pm", request_date_to_period="pm",
            dvz_return_reference="Documented attendance review."))
        leave.with_user(self.hod).action_dvz_hod_approve()
        leave.with_user(self.hr).action_dvz_hr_approve()
        self.assertFalse(leave.dvz_expected_return)
        previous_days = leave.number_of_days
        after_absence = leave.date_to + timedelta(days=1)
        with patch.object(fields.Datetime, "now", return_value=after_absence):
            with self.assertRaisesRegex(UserError, "morning"), self.cr.savepoint():
                leave.with_user(self.hr).action_dvz_mark_failed_return()
        self.assertEqual(leave.request_date_from_period, "pm")
        self.assertEqual(leave.request_date_to_period, "pm")
        self.assertEqual(leave.number_of_days, previous_days)

    def test_prospective_request_cannot_be_converted_to_actual_lwp(self):
        _, employee, paid, _ = self._prepare()
        leave = self.env["hr.leave"].create(self._values(employee, paid,
            dvz_absence_reference="An example reference is not proof a future absence occurred."))
        with self.assertRaises(UserError), self.cr.savepoint():
            leave.with_user(self.hr).action_dvz_convert_unpaid()
        self.assertEqual(leave.holiday_status_id, paid)

    def test_ordinary_unmanaged_type_keeps_native_workflow(self):
        _, employee, _, _ = self._prepare()
        ordinary = self.env["hr.leave.type"].create({"name": "Unmanaged Native Leave",
            "company_id": self.company.id, "requires_allocation": False, "request_unit": "day",
            "leave_validation_type": "hr", "create_calendar_meeting": False})
        leave = self.env["hr.leave"].create(self._values(employee, ordinary))
        self.assertFalse(leave.dvz_policy_id)
        leave.with_user(self.hr).action_approve()
        self.assertEqual(leave.state, "validate")

    def test_native_team_hod_can_approve_without_officer_access(self):
        _, employee, paid, _ = self._prepare()
        native_hod = new_test_user(self.env, login="dvz_workflow_native_team_hod", groups="base.group_user",
            company_id=self.company.id, company_ids=[Command.set(self.company.ids)])
        self.env["hr.employee"].create({"name": "Native Team Approver", "user_id": native_hod.id,
            "company_id": self.company.id})
        employee.leave_manager_id = native_hod
        self.assertFalse(native_hod.has_group("hr_holidays.group_hr_holidays_user"))
        leave = self.env["hr.leave"].with_user(self.staff).create(self._values(employee, paid))
        leave.with_user(native_hod).action_dvz_hod_approve()
        self.assertEqual(leave.dvz_hod_approved_by, native_hod)
        self.assertEqual(leave.state, "validate1")
        leave.with_user(self.hr).action_dvz_hr_approve()
        self.assertEqual(leave.state, "validate")
