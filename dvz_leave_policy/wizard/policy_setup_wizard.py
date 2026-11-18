"""Apply the shared policy to exactly one existing, explicitly selected employee."""

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


TYPE_FIELDS = (
    ("paid", "annual_leave_type_id", "Annual Leave"),
    ("unpaid", "unpaid_leave_type_id", "Leave Without Pay"),
    ("wfh", "wfh_leave_type_id", "Work From Home"),
)
RESULT_FIELDS = frozenset({
    "result_policy_id", "setup_applied", "allocation_id", "allocation_status",
    "allocation_days", "allocation_message", "allocation_period_start", "allocation_period_end",
})


class DvzPolicySetupWizard(models.TransientModel):
    _name = "dvz.policy.setup.wizard"
    _description = "Set Up One Employee"
    _check_company_auto = True

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    employee_id = fields.Many2one("hr.employee", required=True, check_company=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]")
    policy_id = fields.Many2one("dvz.leave.policy", string="Policy", check_company=True,
        domain="[('company_id', '=', company_id), ('state', 'in', ['draft', 'active'])]",
        help="Select a compatible active policy or an unused draft. Leave empty to create the shared-policy draft.")
    policy_state = fields.Selection(related="policy_id.state", readonly=True)
    name = fields.Char(string="Policy Name", required=True, default="Leave and Absence Policy")
    date_from = fields.Date(string="Policy Effective From", required=True, default=fields.Date.context_today)
    date_to = fields.Date(string="Policy Effective Through")
    employment_status = fields.Selection([
        ("permanent", "Permanent"), ("probation", "Probation"),
        ("temporary", "Temporary"), ("unknown", "Not Confirmed")], required=True, default="unknown")
    joining_date = fields.Date(string="Verified Joining Date")
    paid_eligible_date = fields.Date(string="Verified First Paid Leave Date",
        help="Required for permanent employees. Leave it empty during probation if confirmation is not known; never invent a future date.")
    hod_user_id = fields.Many2one("res.users", string="Actual HOD", domain=[("share", "=", False)])
    hr_user_id = fields.Many2one("res.users", string="Actual HR Approver", domain=[("share", "=", False)])
    management_user_id = fields.Many2one("res.users", string="Actual Management Approver",
        domain=[("share", "=", False)])
    annual_leave_type_id = fields.Many2one("hr.leave.type", string="Annual Leave Type", check_company=True)
    unpaid_leave_type_id = fields.Many2one("hr.leave.type", string="Leave Without Pay Type", check_company=True)
    wfh_leave_type_id = fields.Many2one("hr.leave.type", string="Work From Home Type", check_company=True)
    reviewed = fields.Boolean(string="Employee Details, Approvers, Types and Source Choices Verified")
    auto_check_notes = fields.Text(string="Automatic Employee Check", readonly=True, copy=False)
    auto_contract_start = fields.Date(string="Contract Start (Reference Only)", readonly=True, copy=False)
    auto_probation_end = fields.Date(string="Recorded Probation End", readonly=True, copy=False)
    auto_paid_date = fields.Date(string="Possible First Paid Date", readonly=True, copy=False)
    auto_checked_employee_id = fields.Many2one("hr.employee", readonly=True, copy=False)
    probation_end_date = fields.Date(string="Verified Probation End", help="Populate only from a verified employee or contract record. A fixed probation duration is not stated in the supplied policy.")
    as_of_date = fields.Date(string="Allocation Calculation Date", required=True, default=fields.Date.context_today)
    result_policy_id = fields.Many2one("dvz.leave.policy", string="Prepared Policy", readonly=True, copy=False)
    setup_applied = fields.Boolean(string="Applied to Selected Employee", readonly=True, copy=False)
    allocation_id = fields.Many2one("hr.leave.allocation", string="Employee Allocation", readonly=True, copy=False)
    allocation_status = fields.Selection([
        ("create", "Ready to Generate"), ("reuse", "Existing Grant"),
        ("skip", "No Grant Due"), ("error", "Review Required")], readonly=True, copy=False)
    allocation_days = fields.Float(string="Preview Days", readonly=True, copy=False, digits=(16, 4))
    allocation_message = fields.Text(readonly=True, copy=False)
    allocation_period_start = fields.Date(string="Calendar Year Start", readonly=True, copy=False)
    allocation_period_end = fields.Date(string="Calendar Year End", readonly=True, copy=False)

    def _ensure_setup_manager(self):
        if not self.env.su and not self.env.user.has_group("hr_holidays.group_hr_holidays_manager"):
            raise AccessError(_("Only Time Off administrators may set up an employee's leave policy."))
        if any(record.company_id not in self.env.companies for record in self):
            raise AccessError(_("Select a company from your allowed companies."))

    @api.model
    def _policy_defaults(self, policy):
        values = {"policy_id": policy.id, "name": policy.name,
            "date_from": policy.date_from, "date_to": policy.date_to}
        values.update({field: policy[field].id for _kind, field, _label in TYPE_FIELDS})
        values["hr_user_id"] = policy.hr_user_ids.id if len(policy.hr_user_ids) == 1 else False
        values["management_user_id"] = policy.management_user_ids.id if len(policy.management_user_ids) == 1 else False
        return values

    @api.model
    def _employee_defaults(self, employee):
        return {"employee_id": employee.id, "company_id": employee.company_id.id,
            "employment_status": employee.dvz_employment_status,
            "joining_date": employee.dvz_joining_date, "paid_eligible_date": employee.dvz_paid_eligible_date,
            "probation_end_date": employee.dvz_probation_end_date,
            "hod_user_id": employee.leave_manager_id.id}

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        employee = self.env["hr.employee"].browse(values.get("employee_id")).exists()
        if employee:
            employee.check_access("read")
            if employee.company_id not in self.env.companies:
                raise AccessError(_("The selected employee belongs to another allowed-company context."))
            values.update({k: v for k, v in self._employee_defaults(employee).items() if k in field_names})
        company_id = values.get("company_id") or self.env.company.id
        policy = self.env["dvz.leave.policy"].browse(values.get("policy_id")).exists()
        if not policy and employee and employee.dvz_leave_policy_id.state in ("draft", "active"):
            policy = employee.dvz_leave_policy_id
        if not policy:
            preset = self.env.ref("dvz_leave_policy.policy_document_preset", raise_if_not_found=False)
            preset = preset.sudo() if preset else preset
            if preset and preset.company_id.id == company_id and preset.state == "draft" and not preset._has_usage():
                policy = self.env["dvz.leave.policy"].browse(preset.id)
        if policy:
            policy.check_access("read")
            if policy.company_id.id == company_id and policy.company_id in self.env.companies:
                values.update({k: v for k, v in self._policy_defaults(policy).items() if k in field_names})
        return values

    @api.onchange("employee_id")
    def _onchange_employee(self):
        if self.employee_id:
            self.update(self._employee_defaults(self.employee_id))
            self.reviewed = False
            self.auto_check_notes = False
            self.auto_checked_employee_id = False
            self.auto_contract_start = False
            self.auto_probation_end = False
            self.auto_paid_date = False
            if self.employee_id.dvz_leave_policy_id.state in ("draft", "active"):
                self.policy_id = self.employee_id.dvz_leave_policy_id
            elif self.policy_id and self.policy_id.company_id != self.company_id:
                self.policy_id = False

    @api.onchange("policy_id")
    def _onchange_policy(self):
        if self.policy_id:
            self.update(self._policy_defaults(self.policy_id))

    @api.onchange("company_id")
    def _onchange_company(self):
        if self.employee_id and self.employee_id.company_id != self.company_id:
            self.employee_id = False
        if self.policy_id and self.policy_id.company_id != self.company_id:
            self.policy_id = False
        for _kind, field, _label in TYPE_FIELDS:
            if self[field].company_id and self[field].company_id != self.company_id:
                self[field] = False

    @api.model_create_multi
    def create(self, vals_list):
        self._ensure_setup_manager()
        if any(self.env.context.get("default_" + field) for field in RESULT_FIELDS) or any(
                any(values.get(field) for field in RESULT_FIELDS) for values in vals_list):
            raise AccessError(_("Setup results and allocation previews are assigned by the workflow."))
        records = super().create(vals_list)
        records._ensure_setup_manager()
        return records

    def write(self, values):
        self._ensure_setup_manager()
        if RESULT_FIELDS.intersection(values):
            raise AccessError(_("Setup results and allocation previews cannot be edited directly."))
        if any(record.setup_applied for record in self) and set(values) - {"as_of_date"}:
            raise UserError(_("This setup has been applied. Start a new setup to change employee details or policy selection."))
        result = super().write(values)
        self._ensure_setup_manager()
        reset = {}
        if {"policy_id", "company_id", "employee_id"}.intersection(values):
            reset["result_policy_id"] = False
        if "as_of_date" in values or reset:
            reset.update({"allocation_id": False, "allocation_status": False,
                "allocation_days": 0, "allocation_message": False,
                "allocation_period_start": False, "allocation_period_end": False})
            self._internal_write(reset)
        return result

    def _internal_write(self, values):
        return super(DvzPolicySetupWizard, self).write(values)

    @api.constrains("employee_id", "company_id", "policy_id", "joining_date", "paid_eligible_date", "probation_end_date", "date_from", "date_to")
    def _check_identity(self):
        for wizard in self:
            if wizard.employee_id.company_id != wizard.company_id or (
                    wizard.policy_id and wizard.policy_id.company_id != wizard.company_id):
                raise ValidationError(_("The selected employee, policy and setup must belong to the same company."))
            if wizard.paid_eligible_date and wizard.joining_date and wizard.paid_eligible_date < wizard.joining_date:
                raise ValidationError(_("Paid eligibility cannot precede the verified joining date."))
            if wizard.probation_end_date and wizard.joining_date and wizard.probation_end_date < wizard.joining_date:
                raise ValidationError(_("Probation end cannot precede the verified joining date."))
            if wizard.date_to and wizard.date_to < wizard.date_from:
                raise ValidationError(_("Policy end cannot precede policy start."))

    def _lock_setup(self):
        self.ensure_one()
        self._ensure_setup_manager()
        self.env.cr.execute("SELECT id FROM dvz_policy_setup_wizard WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset()
        self._ensure_setup_manager()
        self.env.cr.execute("SELECT id FROM res_company WHERE id = %s FOR UPDATE", [self.company_id.id])
        self.env["dvz.leave.settlement"]._dvz_lock_employees(self.employee_id)
        self.employee_id.invalidate_recordset()

    def _verify_inputs(self, require_review=False):
        if not self.employee_id or not self.employee_id.exists() or not self.employee_id.active:
            raise UserError(_("Select exactly one existing active employee."))
        self.employee_id.check_access("write")
        self._check_identity()
        if not self.joining_date or self.employment_status == "unknown" or (
                self.employment_status == "permanent" and not (self.paid_eligible_date or self.probation_end_date)):
            raise UserError(_("Confirm joining date, employment status and (for permanent employees) an actual first-paid date or recorded probation end. The policy specifies no automatic probation duration."))
        if require_review and not self.reviewed:
            raise UserError(_("Verify the employee details, actual approvers, types and source choices before applying setup."))
        for role, user in ((_("HOD"), self.hod_user_id), (_("HR"), self.hr_user_id),
                           (_("Management"), self.management_user_id)):
            if not user or not user.active or user.share or self.company_id not in user.company_ids:
                raise UserError(_("Select an active internal %(role)s approver with access to this company.", role=role))
            if user == self.employee_id.user_id:
                raise UserError(_("The selected employee cannot approve their own request as %(role)s.", role=role))
        if self.hod_user_id == self.hr_user_id:
            raise UserError(_("Select different HOD and HR approvers."))
        for user in self.hr_user_id | self.management_user_id:
            if not user.has_group("hr_holidays.group_hr_holidays_user"):
                raise UserError(_("HR and Management approvers need native Time Off Officer or Administrator access."))

    def _prepare_types(self, policy):
        selected = self.env["hr.leave.type"]
        for kind, field, label in TYPE_FIELDS:
            if kind == "wfh" and not policy.wfh_enabled:
                continue
            leave_type = self[field]
            desired = policy._type_settings(kind)
            if leave_type:
                leave_type.check_access("read")
                if not leave_type.active or leave_type.company_id and leave_type.company_id != self.company_id:
                    raise UserError(_("Select an active, company-compatible %(type)s type.", type=label))
                if any(leave_type[name] != value for name, value in desired.items()):
                    raise UserError(_("%(type)s does not match this policy. Select a matching type, or leave it blank to create a dedicated type. Existing types will not be reconfigured.", type=leave_type.display_name))
            else:
                leave_type = self.env["hr.leave.type"].create({**desired, "name": label, "company_id": self.company_id.id})
            if leave_type in selected:
                raise UserError(_("Annual Leave, Leave Without Pay and Work From Home require distinct types."))
            selected |= leave_type
            policy[field] = leave_type

    def _prepare_policy(self):
        policy = self.result_policy_id or self.policy_id
        if policy:
            policy.check_access("write")
            if policy.company_id != self.company_id or policy.state not in ("draft", "active"):
                raise UserError(_("Select a draft or active policy in this employee's company."))
            if policy.state == "active":
                if self.hr_user_id not in policy.hr_user_ids or self.management_user_id not in policy.management_user_ids:
                    raise UserError(_("The selected HR and Management approvers must already belong to the active policy. Create a policy revision to change its routes."))
                for _kind, field, _label in TYPE_FIELDS:
                    if self[field] and self[field] != policy[field]:
                        raise UserError(_("Leave types on an active policy cannot be changed by employee setup."))
                return policy
            if policy._has_usage():
                raise UserError(_("This draft has historical use. Create a new policy revision."))
        values = {"name": self.name, "company_id": self.company_id.id,
            "date_from": self.date_from, "date_to": self.date_to,
            "hr_user_ids": [fields.Command.set(self.hr_user_id.ids)],
            "management_user_ids": [fields.Command.set(self.management_user_id.ids)],
            "configuration_reviewed": self.reviewed}
        if policy:
            policy.write(values)
        else:
            policy = self.env["dvz.leave.policy"].create({**self.env["dvz.leave.policy"]._document_preset_values(), **values})
        self._prepare_types(policy)
        return policy

    def _assert_applied(self):
        if not self.setup_applied or not self.result_policy_id or self.result_policy_id.state != "active":
            raise UserError(_("Apply the reviewed setup to this employee before previewing an allocation."))
        employee = self.employee_id
        if (employee.dvz_leave_policy_id != self.result_policy_id or employee.leave_manager_id != self.hod_user_id
                or employee.dvz_joining_date != self.joining_date or employee.dvz_paid_eligible_date != self.paid_eligible_date
                or employee.dvz_probation_end_date != self.probation_end_date
                or employee.dvz_employment_status != self.employment_status):
            raise UserError(_("The employee's setup has changed since this wizard was applied. Start a fresh setup."))

    def action_auto_check_employee(self):
        """Read one selected employee only; never guess probation or silently assign leave.

        Existing DVZ HR dates are verified input candidates. A contract start is NOT
        necessarily the original hire date. A contract trial end is a documented
        probation candidate, but still requires HR review before activation.
        """
        self.ensure_one()
        self._ensure_setup_manager()
        employee = self.employee_id.exists()
        if not employee or not employee.active:
            raise UserError(_("Select an active employee first."))
        employee.check_access("read")
        if employee.company_id != self.company_id:
            raise UserError(_("Select an employee in the setup company."))
        messages = []
        updates = {"auto_checked_employee_id": employee.id, "reviewed": False,
                   "auto_contract_start": False, "auto_probation_end": False,
                   "auto_paid_date": False}
        if employee.dvz_joining_date:
            updates["joining_date"] = employee.dvz_joining_date
            messages.append(_("Joining date: copied from previously verified employee leave field."))
        else:
            messages.append(_("Joining date: missing; confirm from the employee's HR joining record."))
        if employee.dvz_employment_status != "unknown":
            updates["employment_status"] = employee.dvz_employment_status
            messages.append(_("Employment status: copied from the employee's explicit HR setting."))
        else:
            messages.append(_("Employment status: unverified; contract state alone does not prove permanent employment."))
        probation_end = employee.dvz_probation_end_date
        if probation_end:
            updates["probation_end_date"] = probation_end
            messages.append(_("Probation end: copied from previously verified employee leave field."))
        if employee.dvz_paid_eligible_date:
            updates["paid_eligible_date"] = employee.dvz_paid_eligible_date
            messages.append(_("Paid-leave eligibility: copied from previously verified employee leave field."))
        contract_available = "hr.contract" in self.env.registry
        if contract_available:
            Contract = self.env["hr.contract"]
            domain = [("employee_id", "=", employee.id), ("company_id", "=", self.company_id.id)]
            if "state" in Contract._fields:
                domain.append(("state", "=", "open"))
            try:
                contracts = Contract.search(domain, limit=2)
            except AccessError:
                contracts = False
                messages.append(_("Contract records are not readable by this user. Ask an authorized HR officer to verify dates."))
            if contracts and len(contracts) == 1:
                contract = contracts[0]
                if "date_start" in Contract._fields and contract.date_start:
                    updates["auto_contract_start"] = contract.date_start
                    messages.append(_("Contract start %(date)s found. It may differ from original joining date; verify before using it.", date=contract.date_start))
                if "trial_date_end" in Contract._fields and contract.trial_date_end:
                    found = contract.trial_date_end
                    updates["auto_probation_end"] = found
                    # Do not overwrite a recorded employee value if it disagrees.
                    if probation_end and probation_end != found:
                        messages.append(_("CONFLICT: employee probation end differs from the contract trial end %(date)s; HR must resolve it.", date=found))
                    elif not probation_end:
                        updates["probation_end_date"] = found
                        probation_end = found
                        messages.append(_("Probation end %(date)s found in the running contract; review before confirming.", date=found))
            elif contracts and len(contracts) > 1:
                messages.append(_("More than one running contract found. HR must select the correct employment history."))
            elif contracts is not False:
                messages.append(_("No unique running contract was found. Existing employee dates were retained."))
        else:
            messages.append(_("Contract model is not installed; verification uses the employee record only."))
        if probation_end:
            # Inclusive probation end is a configurable policy choice.
            inclusive = self.policy_id.probation_end_inclusive if self.policy_id else True
            proposed = probation_end + timedelta(days=1 if inclusive else 0)
            updates["auto_paid_date"] = proposed
            messages.append(_("Possible first paid-leave date: %(date)s, derived from the recorded probation end and policy setting. Confirm permanent status and the correct date before applying.", date=proposed))
            if (updates.get("employment_status", self.employment_status) == "permanent"
                    and not (updates.get("paid_eligible_date") or self.paid_eligible_date)):
                updates["paid_eligible_date"] = proposed
        else:
            messages.append(_("Probation end: no verified date found. No months or days were invented."))
        hod = employee.leave_manager_id
        if hod and hod.active and not hod.share:
            updates["hod_user_id"] = hod.id
            messages.append(_("HOD: copied from native employee Time Off Approver."))
        else:
            messages.append(_("HOD: select the actual approving user."))
        policy = self.policy_id or employee.dvz_leave_policy_id
        if policy and policy.company_id == self.company_id:
            if len(policy.hr_user_ids) == 1:
                updates["hr_user_id"] = policy.hr_user_ids.id
            if len(policy.management_user_ids) == 1:
                updates["management_user_id"] = policy.management_user_ids.id
        if not updates.get("hr_user_id") and not self.hr_user_id:
            messages.append(_("HR approver: select the real HR user; not inferred from access groups."))
        if not updates.get("management_user_id") and not self.management_user_id:
            messages.append(_("Management approver: select a real user; not inferred from access groups."))
        messages.append(_("Annual entitlement: 24 working days as the supplied document states; new joiner proration, existing allocations and approvals are checked at allocation preview."))
        messages.append(_("REVIEW REQUIRED: automatic inspection does not change employee records, allocate leave, approve requests, or post payroll deductions."))
        updates["auto_check_notes"] = "\n".join(messages)
        self._internal_write(updates)
        return self._reopen()

    def action_create_draft(self):
        with self.env.cr.savepoint():
            self._lock_setup()
            self._verify_inputs()
            if self.setup_applied:
                return self._reopen()
            policy = self._prepare_policy()
            self._internal_write({"policy_id": policy.id, "result_policy_id": policy.id})
        return {"type": "ir.actions.act_window", "name": _("Leave Policy"), "res_model": "dvz.leave.policy",
            "res_id": policy.id, "view_mode": "form", "target": "current",
            "context": {"default_employee_id": self.employee_id.id}}

    def action_apply_employee(self):
        with self.env.cr.savepoint():
            self._lock_setup()
            if self.setup_applied:
                self._assert_applied()
                return self._reopen()
            self._verify_inputs(require_review=True)
            policy = self._prepare_policy()
            if policy.state == "draft":
                policy.action_activate()
            self.employee_id.write({"dvz_leave_policy_id": policy.id,
                "dvz_employment_status": self.employment_status, "dvz_joining_date": self.joining_date,
                "dvz_paid_eligible_date": self.paid_eligible_date, "dvz_probation_end_date": self.probation_end_date,
                "leave_manager_id": self.hod_user_id.id})
            policy._validate_approvers_for_employee(self.employee_id, ["hod", "hr", "management"])
            self._internal_write({"policy_id": policy.id, "result_policy_id": policy.id, "setup_applied": True})
        return self._reopen()

    def _store_preview(self, proposal):
        self._internal_write({"allocation_status": proposal["status"], "allocation_days": proposal["days"],
            "allocation_message": proposal["message"], "allocation_id": proposal.get("allocation_id") or False,
            "allocation_period_start": proposal["period_start"], "allocation_period_end": proposal["period_end"]})

    def action_preview_allocation(self):
        self._lock_setup()
        self._assert_applied()
        try:
            proposal = self.result_policy_id._allocation_values_for_employee(self.employee_id, self.as_of_date)
        except (UserError, ValidationError, AccessError) as exc:
            start, end = self.result_policy_id._get_period(self.as_of_date)
            proposal = {"status": "error", "days": 0, "message": str(exc), "period_start": start, "period_end": end}
        self._store_preview(proposal)
        return self._reopen()

    def action_generate_allocation(self):
        with self.env.cr.savepoint():
            self._lock_setup()
            self._assert_applied()
            proposal = self.result_policy_id._allocation_values_for_employee(self.employee_id, self.as_of_date)
            allocation = self.result_policy_id._create_allocation_for_employee(self.employee_id, self.as_of_date, approve=False)
            proposal["allocation_id"] = allocation.id if allocation else False
            if allocation:
                proposal["status"] = "reuse"
                proposal["message"] = _("The employee's grant is available for normal allocation approval; repeated generation reuses it.")
            self._store_preview(proposal)
        return self._reopen()

    def _reopen(self):
        return {"type": "ir.actions.act_window", "name": _("Set Up One Employee"), "res_model": self._name,
            "res_id": self.id, "view_mode": "form", "target": "new"}
