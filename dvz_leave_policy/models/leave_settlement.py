"""Reconciled annual leave encashment with a manually approved daily rate."""

import math
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare


# An RPC caller can supply a context key, but cannot supply this Python object.
_SETTLEMENT_WRITE_TOKEN = object()
_PROTECTED_FIELDS = {
    "state", "leave_type_id", "unused_days", "amount", "currency_id", "source_allocation_ids",
    "calculated_at", "calculated_by_id", "approved_at", "approved_by_id",
}
_IDENTITY_FIELDS = {"company_id", "policy_id", "employee_id", "period_start", "period_end"}


class DvzLeaveSettlement(models.Model):
    _name = "dvz.leave.settlement"
    _description = "Year-End Leave Encashment"
    _inherit = ["mail.thread"]
    _order = "period_end desc, employee_id, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("Year-End Leave Encashment"))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    policy_id = fields.Many2one("dvz.leave.policy", required=True, check_company=True, ondelete="restrict", tracking=True)
    employee_id = fields.Many2one("hr.employee", required=True, check_company=True, ondelete="restrict", index=True)
    leave_type_id = fields.Many2one(
        "hr.leave.type", related="policy_id.annual_leave_type_id", store=True,
        precompute=True, readonly=True, required=True, index=True,
    )
    period_start = fields.Date(required=True, index=True)
    period_end = fields.Date(required=True, index=True)
    state = fields.Selection([
        ("draft", "Draft"), ("approved", "Approved"),
        ("paid", "Payment Recorded"), ("cancel", "Cancelled"),
    ], required=True, default="draft", readonly=True, copy=False, tracking=True, index=True)
    # Retain the actual native balance; no additional payout rounding applies.
    unused_days = fields.Float(digits=False, min_display_digits=4, readonly=True, copy=False)
    daily_rate = fields.Monetary(currency_field="currency_id", copy=False)
    amount = fields.Monetary(compute="_compute_amount", store=True, currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True)
    rate_reference = fields.Char(copy=False, help="Approval or calculation reference for a manually supplied daily rate.")
    payment_reference = fields.Char(copy=False, tracking=True)
    paid_date = fields.Date(copy=False, tracking=True)
    notes = fields.Text()
    source_allocation_ids = fields.Many2many(
        "hr.leave.allocation", "dvz_settlement_source_allocation_rel", "settlement_id", "allocation_id",
        string="Reconciled Allocations", readonly=True, copy=False,
    )
    calculated_at = fields.Datetime(readonly=True, copy=False)
    calculated_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    approved_at = fields.Datetime(readonly=True, copy=False)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)

    _period_unique = models.Constraint(
        "UNIQUE(company_id, employee_id, leave_type_id, period_start, period_end)",
        "This employee and paid leave type already have a settlement for this period, including cancelled records. "
        "Reuse the existing draft, or reopen its cancelled draft, instead of creating another settlement.",
    )
    _period_order = models.Constraint("CHECK(period_start <= period_end)", "The settlement end must follow its start.")

    @api.depends("unused_days", "daily_rate", "currency_id")
    def _compute_amount(self):
        for record in self:
            record.amount = record.currency_id.round(record.unused_days * record.daily_rate) if record.currency_id else 0.0

    def _ensure_manager(self):
        if not self.env.su and not self.env.user.has_group("hr_holidays.group_hr_holidays_manager"):
            raise AccessError(_("Only Time Off administrators may manage leave settlements."))
        if any(record.company_id not in self.env.companies for record in self):
            raise AccessError(_("Select the settlement company among your allowed companies first."))

    def _internal_write(self, values):
        return self.with_context(_dvz_settlement_write=_SETTLEMENT_WRITE_TOKEN).write(values)

    @api.model_create_multi
    def create(self, vals_list):
        self._ensure_manager()
        prepared = []
        for original in vals_list:
            values = dict(original)
            for key in _PROTECTED_FIELDS & values.keys():
                if key == "state" and values[key] == "draft":
                    continue
                if values[key] not in (False, None, 0, 0.0, "", []):
                    raise AccessError(_("Settlement results must be produced by Calculate Balance and Approve Settlement."))
                values.pop(key)
            if values.get("payment_reference") or values.get("paid_date"):
                raise UserError(_("Record payment details only after approving the settlement."))
            values["state"] = "draft"
            prepared.append(values)
        # default_* context values must not initialize protected workflow fields.
        blocked = _PROTECTED_FIELDS | {"payment_reference", "paid_date"}
        context = {key: value for key, value in self.env.context.items() if key not in {"default_" + field for field in blocked}}
        records = super(DvzLeaveSettlement, self.with_context(context)).create(prepared)
        records._ensure_manager()
        return records

    def write(self, values):
        if self.env.context.get("_dvz_settlement_write") is _SETTLEMENT_WRITE_TOKEN:
            return super().write(values)
        self._ensure_manager()
        self._lock_employee()
        self._ensure_manager()
        if _PROTECTED_FIELDS.intersection(values):
            raise AccessError(_("Calculated balances, results and settlement states cannot be edited directly."))
        for record in self:
            if record.state == "approved":
                if set(values) - {"payment_reference", "paid_date"}:
                    raise UserError(_("An approved settlement is immutable. Only its payment reference and date may be entered."))
                if record.amount <= 0:
                    raise UserError(_("This settlement has no encashment amount and needs no payment record."))
            elif record.state != "draft":
                raise UserError(_("Paid and cancelled settlements cannot be edited. Reopen a cancelled draft to prepare it again."))
            elif {"payment_reference", "paid_date"}.intersection(values):
                raise UserError(_("Record payment details only after approving the settlement."))
        result = super().write(values)
        if _IDENTITY_FIELDS.intersection(values):
            self._clear_calculation()
            # A manual rate approval for one employee/year must not silently
            # follow a draft reassignment. Explicit replacements in the same
            # write are retained for the newly selected settlement identity.
            rate_reset = {}
            if "daily_rate" not in values:
                rate_reset["daily_rate"] = 0.0
            if "rate_reference" not in values:
                rate_reset["rate_reference"] = False
            if rate_reset:
                self._internal_write(rate_reset)
        return result

    def unlink(self):
        self._ensure_manager()
        raise UserError(_("Keep the settlement audit record. Cancel a draft, or edit/reopen that same record to retry."))

    @api.constrains("policy_id", "company_id", "employee_id", "period_start", "period_end")
    def _check_identity(self):
        for record in self:
            if record.employee_id.company_id != record.company_id or record.policy_id.company_id != record.company_id:
                raise ValidationError(_("The employee, policy and settlement must belong to the same company."))
            if not record.policy_id.annual_leave_type_id:
                raise ValidationError(_("The settlement policy needs a paid leave type."))
            if record.period_start and record.period_end:
                if record.policy_id._get_period(record.period_start) != (record.period_start, record.period_end):
                    raise ValidationError(_("Enter exactly one complete leave year for this policy."))

    @api.constrains("unused_days", "daily_rate")
    def _check_numbers(self):
        for record in self:
            if any(not math.isfinite(record[field]) or record[field] < 0 for field in (
                    "unused_days", "daily_rate")):
                raise ValidationError(_("Settlement days and daily rates must be finite, non-negative numbers."))

    @api.onchange("policy_id")
    def _onchange_policy_id(self):
        if self.policy_id:
            self.company_id = self.policy_id.company_id
            current_start, _end = self.policy_id._get_period(fields.Date.context_today(self))
            self.period_start, self.period_end = self.policy_id._get_period(current_start - timedelta(days=1))

    def _clear_calculation(self):
        return self._internal_write({
            "unused_days": 0.0,
            "source_allocation_ids": [fields.Command.clear()],
            "calculated_at": False, "calculated_by_id": False,
        })

    @api.model
    def _dvz_lock_employees(self, employee):
        """Serialize policy accounting under Odoo's REPEATABLE READ isolation.

        A row lock alone cannot refresh an already established transaction
        snapshot. The no-op update preserves every business/audit value while
        advancing the row's MVCC version. A stale waiter then receives the
        serialization failure that Odoo's transaction retry machinery handles.
        This private method is shared by request, allocation and settlement
        workflows; it does not grant any additional ORM access permissions.
        """
        employee_ids = tuple(sorted(employee.ids))
        if employee_ids:
            self.env.cr.execute("SELECT id FROM hr_employee WHERE id IN %s ORDER BY id FOR UPDATE", [employee_ids])
            self.env.cr.execute("UPDATE hr_employee SET write_date = write_date WHERE id IN %s", [employee_ids])
        return True

    def _lock_employee(self):
        record_ids = tuple(sorted(self.ids))
        if record_ids:
            self.env.cr.execute("SELECT id FROM dvz_leave_settlement WHERE id IN %s ORDER BY id FOR UPDATE", [record_ids])
        self.invalidate_recordset()
        self._dvz_lock_employees(self.employee_id)
        self.invalidate_recordset()

    @api.model
    def _dvz_assert_period_open(self, employee, leave_type, date_from, date_to):
        """Called before source changes; the lock also serializes settlement approval."""
        if not employee or not leave_type:
            return True
        first = fields.Date.to_date(date_from) if date_from else fields.Date.to_date("0001-01-01")
        last = fields.Date.to_date(date_to) if date_to else fields.Date.to_date("9999-12-31")
        self._dvz_lock_employees(employee)
        closed = self.sudo().search([
            ("employee_id", "in", employee.ids), ("leave_type_id", "in", leave_type.ids),
            ("state", "in", ["approved", "paid"]),
            ("period_start", "<=", last), ("period_end", ">=", first),
        ], limit=1)
        if closed:
            raise UserError(_("This leave period is closed by settlement %(name)s. Its source leave and allocations cannot be changed.", name=closed.display_name))
        return True

    def _read_balance(self):
        self.ensure_one()
        self._check_identity()
        if self.period_end >= fields.Date.context_today(self.with_context(tz=self.employee_id.tz or "UTC")):
            raise UserError(_("A leave year can be settled only after its final day has ended."))
        if self.policy_id.state not in ("active", "retired"):
            raise UserError(_("Use an active or retired policy with real approved allocations, not a draft policy."))
        if self.policy_id.date_from > self.period_end or self.policy_id.date_to and self.policy_id.date_to < self.period_end:
            raise UserError(_("Select the policy whose effective dates cover the final day of this leave year."))
        if not self.policy_id._employee_eligibility(self.employee_id, self.period_end)["eligible"]:
            raise UserError(_("Review the employee's verified paid-leave eligibility before settling this period."))
        if not self.leave_type_id.requires_allocation:
            raise UserError(_("Year-end settlements require a leave type with approved allocations."))
        if self.leave_type_id.request_unit not in ("day", "half_day"):
            raise UserError(_("The shared policy settles leave measured in days or half-days. Hourly balances are not supported."))

        # Start with a clean context: native balance helpers accept simulation and
        # ignored-leave context keys, which must never influence a real payout.
        employee = self.employee_id.sudo().with_context(
            {}, allowed_company_ids=self.env.companies.ids,
            tz=self.employee_id.tz or "UTC", active_test=False,
        )
        leave_type = employee.env["hr.leave.type"].browse(self.leave_type_id.id)
        allocations = employee.env["hr.leave.allocation"].search([
            ("employee_id", "=", employee.id), ("holiday_status_id", "=", leave_type.id),
            ("state", "in", ["confirm", "validate1", "validate"]),
            ("date_from", "<=", self.period_end),
            "|", ("date_to", "=", False), ("date_to", ">=", self.period_start),
        ])
        if not allocations:
            raise UserError(_("No policy-linked allocation exists for this employee and period. Reconcile the original entitlements before settlement."))
        if allocations.filtered(lambda allocation: allocation.state != "validate"):
            raise UserError(_("Approve or refuse every pending allocation overlapping this period before settlement."))
        source_policies = {self.policy_id.id: self.policy_id}
        for allocation in allocations:
            source_policy = self._check_source_policy(allocation.dvz_policy_id, allocation.dvz_policy_version)
            source_policies[source_policy.id] = source_policy
            if (allocation.dvz_period_start != self.period_start
                    or allocation.dvz_period_end != self.period_end
                    or allocation.allocation_type != "regular"
                    or allocation.date_from < self.period_start
                    or allocation.date_to != self.period_end):
                raise UserError(_("An overlapping allocation has incomplete annual provenance, accruals, or validity inconsistent with this year. Reconcile it before settlement; its balance cannot be guessed."))
            if allocation.date_from < source_policy.date_from or source_policy.date_to and allocation.date_from > source_policy.date_to:
                raise UserError(_("A source allocation starts outside its recorded policy's effective dates. Reconcile the original grant before settlement."))

        leaves = employee.env["hr.leave"].search([
            ("employee_id", "=", employee.id), ("holiday_status_id", "=", leave_type.id),
            ("state", "in", ["confirm", "validate1", "validate"]),
            ("request_date_from", "<=", self.period_end), ("request_date_to", ">=", self.period_start),
        ])
        if leaves.filtered(lambda leave: leave.state != "validate"):
            raise UserError(_("Approve, refuse or cancel every pending leave request overlapping this period before settlement."))
        for leave in leaves:
            first = leave.request_date_from or fields.Datetime.context_timestamp(employee, leave.date_from).date()
            last = leave.request_date_to or fields.Datetime.context_timestamp(employee, leave.date_to).date()
            if first < self.period_start or last > self.period_end:
                raise UserError(_("A leave request crosses the settlement-year boundary. Split and reconcile it before calculating the year-end balance."))
            source_policy = self._check_source_policy(leave.dvz_policy_id, leave.dvz_policy_version)
            source_policies[source_policy.id] = source_policy
            if first < source_policy.date_from or source_policy.date_to and last > source_policy.date_to:
                raise UserError(_("A paid leave request is outside its recorded policy's effective dates. Reconcile that request before settlement."))

        # A revised policy may consume an existing annual grant. Its original
        # allocation provenance remains intact; only an unambiguous timeline of
        # compatible versions is accepted for the year-end rule selection.
        timeline = sorted(source_policies.values(), key=lambda policy: (policy.date_from, policy.id))
        for previous, following in zip(timeline, timeline[1:]):
            previous_end = min(previous.date_to or self.period_end, self.period_end)
            following_start = max(following.date_from, self.period_start)
            if previous_end >= following_start:
                raise UserError(_("Different source policy versions have overlapping effective dates. Close the earlier version before the next one starts, then recalculate this settlement."))

        consumed, recheck = employee._get_consumed_leaves(leave_type, target_date=self.period_end, ignore_future=True)
        detail = consumed.get(employee, {}).get(leave_type, {})
        issues = recheck.get(employee, {}).get(leave_type, {})
        leave_ids = set(leaves.ids)
        if any(item.get("leave_id") in leave_ids and item.get("amount", 0) > 0.0001
               for item in issues.get("excess_days", {}).values()) or (issues.get("to_recheck_leaves", employee.env["hr.leave"]) & leaves):
            raise UserError(_("Odoo reports leave consumption outside the available allocations. Resolve that discrepancy before settling the balance."))
        remaining = 0.0
        for allocation in allocations:
            values = detail.get(allocation)
            if values is None:
                raise UserError(_("Odoo did not return consumption for a source allocation. Reconcile the allocation before settlement."))
            value = values["remaining_leaves"]
            if not math.isfinite(value) or value < -0.0001:
                raise UserError(_("A source allocation has an invalid remaining balance. Reconcile it before settlement."))
            remaining += max(0.0, value)
        return remaining, allocations

    def _check_source_policy(self, policy, recorded_version):
        self.ensure_one()
        if (not policy or policy.state not in ("active", "retired")
                or policy.company_id != self.company_id
                or policy.annual_leave_type_id != self.leave_type_id
                or policy.annual_leave_type_id.request_unit not in ("day", "half_day")
                or policy._get_period(self.period_start) != (self.period_start, self.period_end)
                or policy.version != recorded_version):
            raise UserError(_("A source record has missing or incompatible policy provenance. Every recorded version must match this company, paid leave type, duration unit and leave year."))
        return policy

    def action_calculate(self):
        self._ensure_manager()
        self._lock_employee()
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only draft settlements can be recalculated."))
            unused, allocations = record._read_balance()
            record._internal_write({
                "unused_days": unused,
                "source_allocation_ids": [fields.Command.set(allocations.ids)],
                "calculated_at": fields.Datetime.now(), "calculated_by_id": self.env.uid,
            })
        return True

    def action_approve(self):
        self._ensure_manager()
        self._lock_employee()
        for record in self:
            if record.state != "draft" or not record.calculated_at:
                raise UserError(_("Calculate the draft settlement before approving it."))
            unused, allocations = record._read_balance()
            if (float_compare(unused, record.unused_days, precision_digits=10)
                    or set(allocations.ids) != set(record.source_allocation_ids.ids)):
                raise UserError(_("The source balance or allocations changed after calculation. Calculate Balance again and review the new result."))
            reference = (record.rate_reference or "").strip()
            if unused > 0 and (record.daily_rate <= 0 or not reference):
                raise UserError(_("Encashment requires a positive approved daily rate and its calculation or approval reference."))
            record._internal_write({
                "state": "approved", "approved_at": fields.Datetime.now(), "approved_by_id": self.env.uid,
                "rate_reference": reference,
            })
        return True

    def action_paid(self):
        self._ensure_manager()
        self._lock_employee()
        for record in self:
            if record.state != "approved" or record.amount <= 0:
                raise UserError(_("Only an approved settlement with an encashment amount can have a payment recorded."))
            if not (record.payment_reference or "").strip() or not record.paid_date:
                raise UserError(_("Enter the actual payment reference and payment date before recording the payment."))
            if record.paid_date > fields.Date.context_today(record):
                raise UserError(_("A recorded actual payment cannot have a future payment date."))
            record._internal_write({"state": "paid"})
        return True

    def action_cancel(self):
        self._ensure_manager()
        self._lock_employee()
        if any(record.state != "draft" for record in self):
            raise UserError(_("Only a draft can be cancelled. Approved encashment settlements are final."))
        self._internal_write({"state": "cancel"})
        return True

    def action_reset_draft(self):
        self._ensure_manager()
        self._lock_employee()
        if any(record.state != "cancel" for record in self):
            raise UserError(_("Only a cancelled draft can be reopened."))
        self._internal_write({"state": "draft"})
        self._clear_calculation()
        return True
