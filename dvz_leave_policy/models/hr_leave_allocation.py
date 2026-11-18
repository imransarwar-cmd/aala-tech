import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare


PROVENANCE_FIELDS = frozenset({
    "dvz_policy_id", "dvz_policy_version", "dvz_period_start", "dvz_period_end", "dvz_allocation_key",
})
GENERATED_FINANCIAL_FIELDS = frozenset({
    "employee_id", "holiday_status_id", "date_from", "date_to", "number_of_days",
    "number_of_days_display", "number_of_hours_display", "allocation_type", "accrual_plan_id",
})
RELATED_TYPE_FIELDS = frozenset({"validation_type", "type_request_unit"})
SOURCE_FIELDS = GENERATED_FINANCIAL_FIELDS | {"state"}


class HrLeaveAllocation(models.Model):
    _inherit = "hr.leave.allocation"

    dvz_policy_id = fields.Many2one("dvz.leave.policy", string="Leave Policy", readonly=True,
        copy=False, ondelete="restrict", index=True)
    dvz_policy_version = fields.Integer(string="Policy Version", readonly=True, copy=False)
    dvz_period_start = fields.Date(string="Calendar Year Start", readonly=True, copy=False, index=True)
    dvz_period_end = fields.Date(string="Calendar Year End", readonly=True, copy=False)
    dvz_allocation_key = fields.Char(string="Annual Allocation Reference", readonly=True, copy=False, index=True)

    _dvz_allocation_key_unique = models.Constraint(
        "UNIQUE(dvz_allocation_key)",
        "This annual allocation reference has already been used. Review the existing allocation.",
    )

    @api.model
    def _dvz_require_manager(self):
        if not self.env.su and not self.env.user.has_group("hr_holidays.group_hr_holidays_manager"):
            raise AccessError(_("Only a Time Off administrator can generate policy allocations."))

    @api.model_create_multi
    def create(self, vals_list):
        if any("default_" + name in self.env.context for name in PROVENANCE_FIELDS):
            raise AccessError(_("Policy allocation references cannot be supplied through creation defaults."))
        if any("default_" + name in self.env.context for name in RELATED_TYPE_FIELDS):
            raise AccessError(_("Configure allocation validation and units on the time-off type, not through allocation defaults."))
        for values in vals_list:
            if PROVENANCE_FIELDS.intersection(values):
                raise AccessError(_("Annual policy allocation references are assigned by the checked generation action."))
            if RELATED_TYPE_FIELDS.intersection(values):
                raise AccessError(_("Configure allocation validation and units on the time-off type, not on an allocation."))
        defaults = self.default_get(["employee_id"])
        employee_ids = sorted({values.get("employee_id", defaults.get("employee_id")) for values in vals_list} - {False, None})
        self.env["dvz.leave.settlement"]._dvz_lock_employees(self.env["hr.employee"].browse(employee_ids))
        with self.env.cr.savepoint():
            allocations = super().create(vals_list)
            allocations._dvz_assert_open_periods()
        return allocations

    def _dvz_assert_open_periods(self):
        Settlement = self.env["dvz.leave.settlement"]
        Settlement._dvz_lock_employees(self.employee_id)
        for allocation in self:
            Settlement._dvz_assert_period_open(allocation.employee_id, allocation.holiday_status_id,
                allocation.date_from, allocation.date_to)

    def write(self, values):
        if PROVENANCE_FIELDS.intersection(values):
            raise AccessError(_("Policy allocation provenance cannot be changed directly."))
        if RELATED_TYPE_FIELDS.intersection(values):
            raise AccessError(_("Configure allocation validation and units on the time-off type, not on an allocation."))
        if GENERATED_FINANCIAL_FIELDS.intersection(values) and any(record.dvz_allocation_key for record in self):
            raise UserError(_("Generated annual quantities, employee, type and validity are fixed to their calculation. Reconcile an incorrect grant through an authorized correction; do not rewrite its provenance."))
        if not SOURCE_FIELDS.intersection(values):
            return super().write(values)
        employees = self.employee_id
        if values.get("employee_id"):
            employees |= self.env["hr.employee"].browse(values["employee_id"])
        self.env["dvz.leave.settlement"]._dvz_lock_employees(employees)
        self._dvz_assert_open_periods()
        with self.env.cr.savepoint():
            result = super().write(values)
            self._dvz_assert_open_periods()
        return result

    def copy(self, default=None):
        if any(record.dvz_allocation_key for record in self):
            raise UserError(_("Generate the employee's next calendar year through the allocation action; generated grants cannot be duplicated."))
        return super().copy(default)

    def unlink(self):
        self._dvz_assert_open_periods()
        if any(record.dvz_allocation_key for record in self):
            raise UserError(_("Annual policy allocations retain their grant reference. Refuse an unused proposal instead of deleting it."))
        return super().unlink()

    @api.model
    def _dvz_create_generated(self, values):
        """Private, permission-checked annual grant entry point; no context bypass."""
        self._dvz_require_manager()
        values = dict(values)
        required = PROVENANCE_FIELDS | {"employee_id", "holiday_status_id", "date_from", "date_to", "number_of_days"}
        if any(not values.get(field) for field in required):
            raise UserError(_("Annual allocations require complete policy, employee, amount and validity information."))
        policy = self.env["dvz.leave.policy"].browse(values["dvz_policy_id"]).exists()
        employee = self.env["hr.employee"].browse(values["employee_id"]).exists()
        leave_type = self.env["hr.leave.type"].browse(values["holiday_status_id"]).exists()
        if len(policy) != 1 or len(employee) != 1 or len(leave_type) != 1:
            raise UserError(_("The allocation policy, employee or leave type does not exist."))
        policy.check_access("read")
        employee.check_access("read")
        if policy.company_id != employee.company_id or policy.company_id not in self.env.companies:
            raise UserError(_("The allocation must belong to the selected allowed company."))
        if employee.dvz_leave_policy_id != policy or not policy.active or policy.state != "active":
            raise UserError(_("The active policy must be explicitly assigned to this employee."))
        if leave_type != policy.annual_leave_type_id or not leave_type.requires_allocation or leave_type.unpaid:
            raise UserError(_("An annual grant must use the policy's paid allocation type."))
        if leave_type.company_id and leave_type.company_id != employee.company_id:
            raise UserError(_("The allocation type belongs to another company."))
        if leave_type.allocation_validation_type == "no_validation":
            raise UserError(_("Annual policy allocations require native approval."))
        amount = float(values["number_of_days"])
        if not math.isfinite(amount) or amount <= 0:
            raise ValidationError(_("An annual grant must have a finite positive number of days."))
        start, end = fields.Date.to_date(values["date_from"]), fields.Date.to_date(values["date_to"])
        period_start = fields.Date.to_date(values["dvz_period_start"])
        period_end = fields.Date.to_date(values["dvz_period_end"])
        if (period_start, period_end) != policy._get_period(period_start) or end != period_end or not period_start <= start <= end:
            raise UserError(_("An annual grant must use a complete calendar year and expire on December 31."))
        if int(values["dvz_policy_version"]) != policy.version:
            raise UserError(_("The allocation version must match the policy version."))
        if values.get("allocation_type", "regular") != "regular" or values.get("state", "confirm") != "confirm":
            raise UserError(_("Annual policy grants are regular allocations awaiting native approval."))
        values.update(allocation_type="regular", state="confirm")
        self.env["dvz.leave.settlement"]._dvz_lock_employees(employee)
        if self.sudo().search_count([("dvz_allocation_key", "=", values["dvz_allocation_key"])], limit=1):
            raise UserError(_("This annual grant already exists. Refresh the preview rather than creating another allocation."))
        self.env["dvz.leave.settlement"]._dvz_assert_period_open(employee, leave_type, start, end)
        context = {key: self.env.context[key] for key in ("allowed_company_ids", "lang", "tz") if key in self.env.context}
        with self.env.cr.savepoint():
            allocation = super(HrLeaveAllocation, self.with_context(context)).create([values])
            allocation._dvz_assert_open_periods()
        return allocation.with_env(self.env)

    @api.constrains("dvz_policy_id", "dvz_policy_version", "employee_id", "holiday_status_id",
                    "dvz_period_start", "dvz_period_end", "dvz_allocation_key")
    def _check_dvz_policy_allocation(self):
        for allocation in self.filtered("dvz_policy_id"):
            if allocation.employee_id.company_id != allocation.dvz_policy_id.company_id:
                raise ValidationError(_("The allocation employee and leave policy must belong to the same company."))
            if not allocation.dvz_allocation_key or not allocation.dvz_period_start or not allocation.dvz_period_end:
                raise ValidationError(_("Policy allocations require an annual grant reference and calendar year."))


class DvzLeavePolicyAllocation(models.Model):
    _inherit = "dvz.leave.policy"

    def action_allocate(self):
        self.ensure_one()
        self._ensure_manager()
        return {"type": "ir.actions.act_window", "name": _("Employee Annual Allocation"),
            "res_model": "dvz.leave.allocation.wizard", "view_mode": "form", "target": "new",
            "context": {"default_policy_id": self.id, "default_approve": False}}

    def _allocation_values_for_employee(self, employee, as_of_date):
        """Prepare exactly one employee's annual grant; never scan or assign staff."""
        self.ensure_one()
        employee.ensure_one()
        self._ensure_manager()
        as_of_date = fields.Date.to_date(as_of_date)
        if not as_of_date:
            raise UserError(_("Select the annual calculation date."))
        if self.state != "active" or not self.active:
            raise UserError(_("Only an active policy can generate an annual allocation."))
        if self.company_id not in self.env.companies or employee.company_id != self.company_id:
            raise UserError(_("The selected employee must belong to the policy's allowed company."))
        employee.check_access("read")
        if not employee.active:
            raise UserError(_("Archived employees cannot receive a new annual allocation."))
        if self._get_for_employee(employee, as_of_date) != self:
            raise UserError(_("Explicitly assign this policy to the selected employee before preparing an allocation."))
        self._validate_activation()
        self.env["dvz.leave.settlement"]._dvz_lock_employees(employee)
        year_start, year_end = self._get_period(as_of_date)
        info = self._employee_eligibility(employee, as_of_date)
        result = {"employee_id": employee.id, "period_start": year_start, "period_end": year_end,
            "days": 0.0, "status": "skip", "message": info["reason"], "allocation_id": False, "values": {}}
        if not info["eligible"]:
            if not info.get("joining_date") or employee.dvz_employment_status == "unknown" or (
                    employee.dvz_employment_status == "permanent" and not info.get("first_paid_date")):
                raise UserError(info["reason"] or _("Complete the employee's verified eligibility dates."))
            return result
        amount = self._compute_entitlement(employee, year_start, year_end, as_of_date)
        valid_from = max(year_start, info["first_paid_date"], self.date_from)
        if not math.isfinite(amount) or amount < 0:
            raise UserError(_("The annual calculation returned an invalid entitlement."))
        result["days"] = amount
        if not amount:
            result["message"] = _("No annual entitlement is due.")
            return result
        if valid_from > year_end:
            raise UserError(_("Paid eligibility is outside this calendar year."))
        # Retain the existing annual reference format for safe reruns/upgrades.
        key = "dvz:%s:%s:%s:%s:annual:annual" % (
            self.company_id.id, employee.id, self.annual_leave_type_id.id, year_start.isoformat())
        values = {"name": _("%(policy)s - %(employee)s - %(year)s",
                    policy=self.name, employee=employee.name, year=year_start.year),
            "employee_id": employee.id, "holiday_status_id": self.annual_leave_type_id.id,
            "number_of_days": amount, "date_from": valid_from, "date_to": year_end, "allocation_type": "regular",
            "dvz_policy_id": self.id, "dvz_policy_version": self.version,
            "dvz_period_start": year_start, "dvz_period_end": year_end, "dvz_allocation_key": key,
            "notes": _("Policy version %(version)s; calculation date %(date)s; annual calendar-year grant; actual-day proration from %(basis)s; rounding %(step)s %(rounding)s.",
                version=self.version, date=as_of_date, basis=self.proration_basis,
                step=self.rounding_step, rounding=self.rounding_method)}
        Allocation = self.env["hr.leave.allocation"]
        existing_key = Allocation.sudo().search([("dvz_allocation_key", "=", key)], limit=2)
        if len(existing_key) > 1:
            raise UserError(_("Duplicate annual grant references require reconciliation."))
        if existing_key:
            if existing_key.state == "refuse":
                raise UserError(_("The existing annual grant was refused. Review it; generation will not silently recreate it."))
            exact = (existing_key.employee_id == employee and existing_key.holiday_status_id == self.annual_leave_type_id
                and existing_key.dvz_policy_id == self and existing_key.dvz_policy_version == self.version
                and existing_key.date_from == valid_from and existing_key.date_to == year_end
                and existing_key.dvz_period_start == year_start and existing_key.dvz_period_end == year_end
                and float_compare(existing_key.number_of_days, amount, precision_digits=4) == 0)
            if not exact:
                raise UserError(_("An existing annual grant has a different policy, validity or quantity. Reconcile it before generating another grant."))
            result.update(status="reuse", message=_("The existing annual grant will be reused."),
                allocation_id=existing_key.id, values=values)
        else:
            result.update(status="create", message=_("Ready to generate one annual grant."), values=values)
        # A newly selected paid type must not duplicate an existing native paid
        # balance. Review all paid allocations for this one employee/year only.
        existing = Allocation.sudo().search([
            ("employee_id", "=", employee.id), ("state", "!=", "refuse"),
            ("date_from", "<=", year_end), "|", ("date_to", "=", False), ("date_to", ">=", year_start),
            ("holiday_status_id.requires_allocation", "=", True), ("holiday_status_id.unpaid", "=", False),
            ("holiday_status_id.time_type", "=", "leave")])
        conflicts = existing - existing_key
        if conflicts:
            raise UserError(_("Existing paid allocations overlap this employee's calendar year: %s. Reconcile them before generation; no additional balance will be created automatically.",
                ", ".join(str(item) for item in conflicts.ids)))
        self.env["dvz.leave.settlement"]._dvz_assert_period_open(
            employee, self.annual_leave_type_id, valid_from, year_end)
        return result

    def _create_allocation_for_employee(self, employee, as_of_date, approve=False):
        """Generate/reuse one annual grant, with ordinary native approval rights."""
        self.ensure_one()
        employee.ensure_one()
        Allocation = self.env["hr.leave.allocation"]
        Allocation._dvz_require_manager()
        with self.env.cr.savepoint():
            self.env["dvz.leave.settlement"]._dvz_lock_employees(employee)
            proposal = self._allocation_values_for_employee(employee, as_of_date)
            if proposal["status"] == "skip":
                return Allocation
            allocation = (Allocation.browse(proposal["allocation_id"]) if proposal["status"] == "reuse" else
                          Allocation._dvz_create_generated(proposal["values"]))
            if approve and allocation.state != "validate":
                if allocation.state not in ("confirm", "validate1"):
                    raise UserError(_("The existing allocation is no longer awaiting approval."))
                allocation.action_approve()
                if allocation.state != "validate":
                    raise UserError(_("Complete the remaining native allocation approval in Odoo."))
            return allocation

