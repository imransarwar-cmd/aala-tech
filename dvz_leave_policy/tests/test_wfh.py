"""Integration cases for source-policy WFH commitments and verified task delivery."""
from datetime import timedelta
from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestWfhPolicy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.hod = new_test_user(cls.env, login="dvz_options_hod", groups="hr_holidays.group_hr_holidays_manager",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        cls.hr = new_test_user(cls.env, login="dvz_options_hr", groups="hr_holidays.group_hr_holidays_manager",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        cls.outsider = new_test_user(cls.env, login="dvz_options_other_officer", groups="hr_holidays.group_hr_holidays_manager",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        cls.staff = new_test_user(cls.env, login="dvz_options_staff", groups="base.group_user",
            company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        for user in (cls.hod, cls.hr):
            cls.env["hr.employee"].create({"name": user.name, "user_id": user.id, "company_id": cls.company.id})
        cls.calendar = cls.env["resource.calendar"].create({"name": "WFH Policy Test Calendar",
            "company_id": cls.company.id, "tz": "UTC", "attendance_ids": [Command.clear()] + [
                Command.create({"name": "%s %s" % (day, period), "dayofweek": str(day),
                    "day_period": period, "hour_from": start, "hour_to": stop})
                for day in range(5) for period, start, stop in (("morning", 8, 12), ("afternoon", 13, 17))]})
        cls.day = fields.Date.today().replace(day=1) + relativedelta(months=2)
        while cls.day.weekday() != 0:
            cls.day += timedelta(days=1)

    def _prepare(self, **changes):
        policy = self.env["dvz.leave.policy"].create({
            "name": "WFH Policy Test Policy", "company_id": self.company.id, "date_from": "2020-01-01",
            "wfh_enabled": True, "exception_mode": "disabled", "approval_mode": "both",
            "wfh_approval_mode": "both",
            "hr_user_ids": [Command.set(self.hr.ids)], "full_day_notice_days": 0,
            "half_day_notice_days": 0, "wfh_notice_days": 0,
            "require_prior_approval": False, "wfh_require_prior_approval": False, **changes})
        types = {}
        for kind, field in (("paid", "annual_leave_type_id"), ("unpaid", "unpaid_leave_type_id"), ("wfh", "wfh_leave_type_id")):
            types[kind] = self.env["hr.leave.type"].create({**policy._type_settings(kind),
                "name": "WFH Test %s" % kind, "company_id": self.company.id, "create_calendar_meeting": False})
            policy[field] = types[kind]
        policy.action_activate()
        employee = self._employee(policy, "WFH Test Staff", self.staff)
        return policy, employee, types

    def _employee(self, policy, name, user=None):
        employee = self.env["hr.employee"].create({"name": name, "company_id": self.company.id,
            "user_id": user.id if user else False, "leave_manager_id": self.hod.id,
            "dvz_leave_policy_id": policy.id, "dvz_employment_status": "permanent",
            "dvz_joining_date": "2020-01-01", "dvz_paid_eligible_date": "2020-04-01",
            "resource_calendar_id": self.calendar.id, "tz": "UTC"})
        start, end = policy._get_period(self.day)
        allocation = self.env["hr.leave.allocation"].create({"name": "WFH Test Allocation",
            "employee_id": employee.id, "holiday_status_id": policy.annual_leave_type_id.id,
            "date_from": start, "date_to": end, "number_of_days": policy.annual_days, "allocation_type": "regular"})
        allocation.action_approve()
        return employee

    def _values(self, employee, leave_type, **changes):
        return {"name": "Documented request reason", "employee_id": employee.id,
            "holiday_status_id": leave_type.id, "request_date_from": self.day, "request_date_to": self.day,
            "request_date_from_period": "am", "request_date_to_period": "pm",
            "dvz_wfh_available": True, "dvz_wfh_communication": True, **changes}

    def _approve(self, leave):
        leave.with_user(self.hod).action_dvz_hod_approve()
        leave.with_user(self.hr).action_dvz_hr_approve()
        self.assertEqual(leave.state, "validate")


    def test_wfh_commitments_and_probation_filter(self):
        _, employee, types = self._prepare(wfh_availability_required=True, wfh_communication_required=True)
        with self.assertRaisesRegex(ValidationError, "availability"), self.cr.savepoint():
            self.env["hr.leave"].create(self._values(employee, types["wfh"], dvz_wfh_available=False))
        with self.assertRaisesRegex(ValidationError, "communication"), self.cr.savepoint():
            self.env["hr.leave"].create(self._values(employee, types["wfh"], dvz_wfh_available=True, dvz_wfh_communication=False))
        employee.dvz_employment_status = "probation"
        with self.assertRaisesRegex(ValidationError, "policy eligibility"), self.cr.savepoint():
            self.env["hr.leave"].create(self._values(employee, types["wfh"],
                dvz_wfh_available=True, dvz_wfh_communication=True))

    def test_employee_wizard_sends_actual_recipients_and_current_text_proof(self):
        _, employee, types = self._prepare()
        leave = self.env["hr.leave"].create(self._values(employee, types["wfh"]))
        self._approve(leave)
        wizard = self.env["dvz.wfh.update.wizard"].with_user(self.staff).create({
            "leave_id": leave.id, "task_update": "Completed the assigned review."})
        with patch.object(fields.Datetime, "now", return_value=leave.date_from + timedelta(minutes=1)):
            wizard.with_context(mail_notify_force_send=False).action_send()
        self.assertEqual(leave.dvz_task_update_sent_by, self.staff)
        self.assertEqual(set(leave.dvz_task_update_recipient_ids.ids), set((self.hod | self.hr).ids))
        self.assertEqual(set(leave.dvz_task_update_message_id.partner_ids.ids), set((self.hod | self.hr).partner_id.ids))
        self.assertTrue(leave.dvz_task_update_completed)
        leave.with_user(self.hr).write({"dvz_task_update": "A new update still needs sending."})
        self.assertFalse(leave.dvz_task_update_completed)
        self.assertEqual(leave.dvz_task_update_sent_by, self.staff)

    def test_task_update_actor_and_audit_cannot_be_spoofed(self):
        _, employee, types = self._prepare()
        leave = self.env["hr.leave"].create(self._values(employee, types["wfh"]))
        with self.assertRaises(AccessError), self.cr.savepoint():
            leave.with_user(self.outsider).action_dvz_send_task_update("Not the owner or an assigned approver.")
        with self.assertRaises(AccessError), self.cr.savepoint():
            leave.with_user(self.hr).write({"dvz_task_update_sent_by": self.staff.id})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            leave.with_user(self.staff).action_dvz_send_task_update({"state": "validate"})

    def test_send_timing_allows_draft_but_prevents_future_completion(self):
        _, employee, types = self._prepare()
        leave = self.env["hr.leave"].create(self._values(employee, types["wfh"]))
        leave.with_user(self.staff).action_dvz_save_task_update("Draft progress update.")
        self.assertFalse(leave.dvz_task_update_completed)
        with self.assertRaisesRegex(UserError, "after the WFH period has started"), self.cr.savepoint():
            leave.with_user(self.staff).action_dvz_send_task_update()
        with patch.object(fields.Datetime, "now", return_value=leave.date_from + timedelta(minutes=1)):
            leave.with_user(self.staff).with_context(mail_notify_force_send=False).action_dvz_send_task_update("Completed the first task.")
        self.assertTrue(leave.dvz_task_update_completed)
        leave.with_user(self.staff).write({"request_date_to": self.day + timedelta(days=1)})
        self.assertFalse(leave.dvz_task_update_completed)
        self.assertEqual(leave.dvz_task_update_sent_by, self.staff)


