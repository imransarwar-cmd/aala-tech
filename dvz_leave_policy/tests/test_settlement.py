"""Source-policy year-end encashment tests for an isolated Odoo database."""

from datetime import date, timedelta

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestLeaveSettlements(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        year = fields.Date.today().year - 1
        cls.period_start, cls.period_end = date(year, 1, 1), date(year, 12, 31)
        cls.hod, cls.hr, cls.management = [new_test_user(
            cls.env, login="dvz_encashment_test_%s" % role,
            groups="hr_holidays.group_hr_holidays_manager",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)],
        ) for role in ("hod", "hr", "management")]
        with freeze_time(cls.period_start):
            for user in (cls.hod, cls.hr, cls.management):
                cls.env["hr.employee"].create({
                    "name": user.name, "user_id": user.id, "company_id": cls.company.id,
                })
            cls.employee = cls.env["hr.employee"].create({
                "name": "Encashment Test Employee", "company_id": cls.company.id,
                "leave_manager_id": cls.hod.id,
                "resource_calendar_id": cls.company.resource_calendar_id.id,
                "dvz_employment_status": "permanent", "dvz_joining_date": cls.period_start,
                "dvz_paid_eligible_date": cls.period_start,
            })

    def _case(self):
        policy = self.env["dvz.leave.policy"].create({
            "name": "Encashment Test Policy", "company_id": self.company.id,
            "date_from": self.period_start, "wfh_enabled": False,
            "hr_user_ids": [Command.set(self.hr.ids)],
            "management_user_ids": [Command.set(self.management.ids)],
        })
        paid = self.env["hr.leave.type"].create({
            **policy._type_settings("paid"), "name": "Encashment Paid Type",
            "company_id": self.company.id, "create_calendar_meeting": False,
        })
        unpaid = self.env["hr.leave.type"].create({
            **policy._type_settings("unpaid"), "name": "Encashment Unpaid Type",
            "company_id": self.company.id, "create_calendar_meeting": False,
        })
        policy.write({"annual_leave_type_id": paid.id, "unpaid_leave_type_id": unpaid.id})
        policy.action_activate()
        self.employee.dvz_leave_policy_id = policy
        allocation = policy._create_allocation_for_employee(self.employee, self.period_start, approve=True)
        settlement = self.env["dvz.leave.settlement"].create(self._settlement_values(policy))
        return policy, allocation, settlement

    def _settlement_values(self, policy):
        return {
            "name": "Test annual leave encashment", "company_id": self.company.id,
            "employee_id": self.employee.id, "policy_id": policy.id,
            "period_start": self.period_start, "period_end": self.period_end,
        }

    def _approved_leave(self, policy, on_date=None):
        workday = on_date or self.period_start.replace(month=2)
        workday += timedelta(days=(7 - workday.weekday()) % 7)
        with freeze_time(workday - timedelta(days=2)):
            leave = self.env["hr.leave"].create({
                "name": "Reconciled paid leave", "employee_id": self.employee.id,
                "holiday_status_id": policy.annual_leave_type_id.id,
                "request_date_from": workday, "request_date_to": workday,
                "request_date_from_period": "am", "request_date_to_period": "pm",
            })
            leave.with_user(self.hod).action_dvz_hod_approve()
            leave.with_user(self.hr).action_dvz_hr_approve()
        self.assertEqual(leave.state, "validate")
        self.assertGreater(leave.number_of_days, 0)
        return leave

    def test_full_unused_balance_uses_only_manual_approved_rate(self):
        _policy, source, settlement = self._case()
        settlement.action_calculate()
        self.assertEqual(settlement.unused_days, source.number_of_days)
        self.assertEqual(settlement.daily_rate, 0)
        settlement.write({"daily_rate": 100, "rate_reference": "Approved rate memo"})
        self.assertEqual(settlement.amount, 2400)
        settlement.action_approve()
        self.assertEqual(settlement.state, "approved")
        with self.assertRaises(UserError):
            settlement.action_approve()

    def test_positive_rate_and_reference_are_required_for_encashment(self):
        _policy, _source, settlement = self._case()
        settlement.action_calculate()
        with self.assertRaises(UserError):
            settlement.action_approve()
        settlement.write({"daily_rate": 100})
        with self.assertRaises(UserError):
            settlement.action_approve()
        settlement.write({"rate_reference": "Approved rate memo"})
        settlement.action_approve()
        self.assertEqual(settlement.state, "approved")

    def test_rpc_context_cannot_forge_balance_or_approval(self):
        policy, _source, settlement = self._case()
        with self.assertRaises(AccessError):
            settlement.with_context(_dvz_settlement_write=True).write({"unused_days": 1000})
        with self.assertRaises(AccessError):
            settlement.write({"state": "approved"})
        with self.assertRaises(AccessError):
            self.env["dvz.leave.settlement"].create({**self._settlement_values(policy), "state": "approved"})
        with self.assertRaises(UserError):
            settlement.action_approve()

    def test_creation_defaults_cannot_forge_approved_results(self):
        policy, _source, _settlement = self._case()
        values = self._settlement_values(policy)
        values.update({"period_start": self.period_start.replace(year=self.period_start.year + 1),
                       "period_end": self.period_end.replace(year=self.period_end.year + 1)})
        draft = self.env["dvz.leave.settlement"].with_context(
            default_state="approved", default_unused_days=1000, default_amount=100000,
        ).create(values)
        self.assertEqual(draft.state, "draft")
        self.assertEqual(draft.unused_days, 0)
        self.assertEqual(draft.amount, 0)

    def test_pending_allocation_blocks_settlement(self):
        policy, _source, settlement = self._case()
        self.env["hr.leave.allocation"].create({
            "employee_id": self.employee.id, "holiday_status_id": policy.annual_leave_type_id.id,
            "number_of_days": 1, "date_from": self.period_start, "date_to": self.period_end,
        })
        with self.assertRaises(UserError):
            settlement.action_calculate()

    def test_pending_leave_on_final_day_blocks_settlement(self):
        policy, _source, settlement = self._case()
        if self.period_end.weekday() > 4:
            self.env["resource.calendar.attendance"].create({
                "name": "Final-day test attendance", "calendar_id": self.employee.resource_calendar_id.id,
                "dayofweek": str(self.period_end.weekday()), "day_period": "morning",
                "hour_from": 9, "hour_to": 17,
            })
        with freeze_time(self.period_end - timedelta(days=2)):
            pending = self.env["hr.leave"].create({
                "name": "Pending leave on the final calendar day", "employee_id": self.employee.id,
                "holiday_status_id": policy.annual_leave_type_id.id,
                "request_date_from": self.period_end, "request_date_to": self.period_end,
                "request_date_from_period": "am", "request_date_to_period": "pm",
            })
        self.assertEqual(pending.state, "confirm")
        with self.assertRaisesRegex(UserError, "pending leave request"):
            settlement.action_calculate()

    def test_unlinked_approved_allocation_is_not_guessed_into_balance(self):
        policy, _source, settlement = self._case()
        manual = self.env["hr.leave.allocation"].create({
            "employee_id": self.employee.id, "holiday_status_id": policy.annual_leave_type_id.id,
            "number_of_days": 1, "date_from": self.period_start, "date_to": self.period_end,
        })
        manual.action_approve()
        with self.assertRaises(UserError):
            settlement.action_calculate()

    def test_approved_period_and_payment_record_are_immutable(self):
        policy, _source, settlement = self._case()
        settlement.write({"daily_rate": 200, "rate_reference": "Approved rate memo"})
        settlement.action_calculate()
        settlement.action_approve()
        with self.assertRaises(UserError):
            settlement.write({"daily_rate": 500})
        with self.assertRaises(UserError):
            settlement.action_cancel()
        with self.assertRaises(UserError):
            settlement._dvz_assert_period_open(self.employee, policy.annual_leave_type_id, self.period_start, self.period_end)
        with self.assertRaises(UserError):
            settlement.action_paid()
        settlement.write({"payment_reference": "Actual payment reference", "paid_date": fields.Date.today()})
        settlement.action_paid()
        self.assertEqual(settlement.state, "paid")
        with self.assertRaises(UserError):
            settlement.write({"payment_reference": "Replacement"})

    def test_cancelled_draft_is_reopened_without_another_settlement(self):
        _policy, _source, settlement = self._case()
        original_id = settlement.id
        settlement.action_calculate()
        settlement.action_cancel()
        settlement.action_reset_draft()
        self.assertEqual(settlement.id, original_id)
        self.assertEqual(settlement.state, "draft")
        self.assertFalse(settlement.calculated_at)
        settlement.action_calculate()
        self.assertEqual(settlement.unused_days, 24)

    def test_native_leave_consumption_cannot_be_hidden_with_context(self):
        policy, source, settlement = self._case()
        leave = self._approved_leave(policy)
        settlement.with_context(ignored_leave_ids=leave.ids).action_calculate()
        self.assertEqual(settlement.unused_days, source.number_of_days - leave.number_of_days)

    def test_approval_rechecks_actual_balance_after_new_consumption(self):
        policy, _source, settlement = self._case()
        settlement.write({"daily_rate": 100, "rate_reference": "Approved rate memo"})
        settlement.action_calculate()
        self._approved_leave(policy)
        with self.assertRaises(UserError):
            settlement.action_approve()
        settlement.action_calculate()
        settlement.action_approve()
        self.assertEqual(settlement.state, "approved")

    def test_compatible_midyear_revision_keeps_original_grant_provenance(self):
        original, source, settlement = self._case()
        boundary = self.period_start.replace(month=7)
        original.write({"date_to": boundary - timedelta(days=1)})
        revision = self.env["dvz.leave.policy"].browse(original.action_revision()["res_id"])
        revision.write({"date_from": boundary, "date_to": self.period_end})
        revision.action_activate()
        self.employee.dvz_leave_policy_id = revision
        leave = self._approved_leave(revision, boundary)
        next_policy = self.env["dvz.leave.policy"].browse(revision.action_revision()["res_id"])
        next_policy.write({"date_from": self.period_end + timedelta(days=1), "date_to": False})
        next_policy.action_activate()
        self.employee.dvz_leave_policy_id = next_policy
        revision.action_retire()
        settlement.write({"policy_id": revision.id, "daily_rate": 150, "rate_reference": "Approved year-end rate"})
        settlement.action_calculate()
        self.assertEqual(source.dvz_policy_id, original)
        self.assertEqual(settlement.unused_days, source.number_of_days - leave.number_of_days)
        settlement.action_approve()
        self.assertEqual(settlement.state, "approved")

    def test_only_an_ended_year_can_be_settled(self):
        _policy, _source, settlement = self._case()
        settlement.write({"period_start": self.period_start.replace(year=self.period_start.year + 1),
                          "period_end": self.period_end.replace(year=self.period_end.year + 1)})
        with self.assertRaises(UserError):
            settlement.action_calculate()
