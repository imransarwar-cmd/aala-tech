import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from . import policy_engine


APPROVAL_MODES = [("none", "No Approval"), ("hod", "Department Approver"),
                  ("hr", "HR Approver"), ("both", "Department and HR Approvers")]


class DvzLeavePolicy(models.Model):
    _name = "dvz.leave.policy"
    _description = "Leave Policy"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, date_from desc, version desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True)
    state = fields.Selection([("draft", "Draft"), ("active", "Active"), ("retired", "Retired")],
        default="draft", required=True, tracking=True, copy=False)
    version = fields.Integer(default=1, required=True, readonly=True, copy=False)
    date_from = fields.Date(string="Effective From", required=True, default=fields.Date.context_today, tracking=True)
    date_to = fields.Date(string="Effective Through", tracking=True)
    annual_leave_type_id = fields.Many2one("hr.leave.type", string="Paid Leave Type", check_company=True)
    unpaid_leave_type_id = fields.Many2one("hr.leave.type", string="Unpaid Leave Type", check_company=True)
    wfh_leave_type_id = fields.Many2one("hr.leave.type", string="Work From Home Type", check_company=True)

    annual_days = fields.Float(string="Annual Entitlement (Working Days)", default=24.0, digits=(16, 4), tracking=True)
    proration_basis = fields.Selection([("joining", "Joining Date"), ("eligibility", "Paid Eligibility Date")],
        default="joining", required=True,
        help="The source preset prorates new joiners from their joining date using actual calendar days in January–December. Eligibility-date proration is an explicitly editable interpretation. Neither basis permits paid leave during probation.")
    rounding_step = fields.Float(string="Rounding Increment (Days)", default=0.5, digits=(16, 4),
        help="Editable calculation convention: 0 preserves precision; 0.5 rounds to half days. The source policy does not specify fractional-day rounding.")
    rounding_method = fields.Selection([("down", "Down"), ("nearest", "Nearest"), ("up", "Up")],
        default="down", required=True)
    probation_end_inclusive = fields.Boolean(string="Probation End Date Is Last Unpaid Day", default=True,
        help="Eligibility starts the following day when enabled. An explicitly verified First Paid Leave Date takes priority. No probation length is assumed.")

    request_unit = fields.Selection([("day", "Days"), ("half_day", "Full and Half Days")],
        default="half_day", required=True)
    include_public_holidays = fields.Boolean(string="Count Public Holidays as Leave", default=False)
    approval_mode = fields.Selection(APPROVAL_MODES, default="both", required=True, string="Paid Leave Approval")
    unpaid_approval_mode = fields.Selection(APPROVAL_MODES, default="hr", required=True, string="Unpaid Leave Approval")
    hr_user_ids = fields.Many2many("res.users", "dvz_leave_policy_hr_user_rel", "policy_id", "user_id",
        string="HR Approvers", domain=[("share", "=", False)],
        help="If empty, active Time Off administrators of the employee's company may approve. The HOD is the employee's native Time Off approver.")
    management_user_ids = fields.Many2many("res.users", "dvz_leave_policy_management_user_rel", "policy_id", "user_id",
        string="Management Exception Approvers", domain=[("share", "=", False)])

    full_day_notice_days = fields.Integer(default=0, string="Full-Day Calendar Notice Days")
    half_day_notice_days = fields.Integer(default=1, string="Half-Day Calendar Notice Days")
    require_prior_approval = fields.Boolean(default=True)
    allow_emergency = fields.Boolean(default=True)
    emergency_waives_notice = fields.Boolean(default=True,
        help="An emergency may waive notice timing; it never creates an approval.")
    exception_mode = fields.Selection([("disabled", "No Exceptions"),
        ("all_three", "Management, Department and HR Approval")], default="all_three", required=True)
    half_day_return_action = fields.Selection([("none", "No Follow-up"), ("review", "Flag for HR Review"),
        ("full_day", "Convert Verified Failure to Full Day")], default="full_day", required=True,
        help="A same-day failed return requires HR-verified evidence. No attendance job automatically classifies an absence.")
    unauthorized_action = fields.Selection([("review", "Review Only"),
        ("unpaid", "Convert Verified Actual Absence to Unpaid")], default="unpaid", required=True)

    wfh_enabled = fields.Boolean(default=True, string="Enable Work From Home")
    wfh_approval_mode = fields.Selection(APPROVAL_MODES, default="both", required=True, string="Work From Home Approval")
    wfh_notice_days = fields.Integer(default=0, string="WFH Calendar Notice Days")
    wfh_require_prior_approval = fields.Boolean(default=True)
    wfh_unapproved_action = fields.Selection([("review", "Review Only"),
        ("unpaid", "Convert Verified Actual Absence to Unpaid")], default="unpaid", required=True)
    wfh_task_update_required = fields.Boolean(default=True)
    wfh_availability_required = fields.Boolean(default=True, string="Require Availability During Working Hours")
    wfh_communication_required = fields.Boolean(default=True, string="Require Team Communication")
    notes = fields.Html(string="Policy Notes")

    def _ensure_manager(self):
        if not self.env.su and not (self.env.user.has_group("hr_holidays.group_hr_holidays_manager") or
                                   self.env.user.has_group("hr.group_hr_manager")):
            raise AccessError(_("Only HR or Time Off administrators may configure leave policies."))

    @api.model_create_multi
    def create(self, vals_list):
        self._ensure_manager()
        if self.env.context.get("default_state", "draft") != "draft":
            raise UserError(_("Create a draft policy and activate it through the activation action."))
        clean = []
        for values in vals_list:
            if values.get("state", "draft") != "draft":
                raise UserError(_("Create a draft policy and activate it through the activation action."))
            clean.append({**values, "state": "draft"})
        return super().create(clean)

    def _has_usage(self):
        self.ensure_one()
        for model in ("hr.leave", "hr.leave.allocation"):
            if "dvz_policy_id" in self.env[model]._fields and self.env[model].sudo().search_count([
                ("dvz_policy_id", "=", self.id)], limit=1):
                return True
        if "dvz.leave.settlement" in self.env and self.env["dvz.leave.settlement"].sudo().search_count([
            ("policy_id", "=", self.id)], limit=1):
            return True
        return False

    def write(self, values):
        self._ensure_manager()
        if "state" in values and any(values["state"] != record.state for record in self):
            raise UserError(_("Use the policy activation or retirement action to change its state."))
        if "version" in values and any(values["version"] != record.version for record in self):
            raise UserError(_("Create a revision instead of changing an existing version number."))
        lifecycle = {"name", "active", "notes", "date_to", "state", "message_follower_ids", "activity_ids"}
        changes = set(values) - lifecycle
        if changes:
            for record in self:
                changed = any(record[field] != values[field] for field in changes if field in record._fields)
                if changed and (record.state != "draft" or record._has_usage()):
                    raise UserError(_("Active, retired or used policy rules are fixed to their version. Create a revision before changing configuration."))
        if values.get("date_to"):
            new_end = fields.Date.to_date(values["date_to"])
            for record in self:
                if "dvz_policy_id" in self.env["hr.leave"]._fields and self.env["hr.leave"].sudo().search_count([
                    ("dvz_policy_id", "=", record.id), ("state", "not in", ["cancel", "refuse"]),
                    ("request_date_to", ">", new_end)], limit=1):
                    raise UserError(_("The new policy end date would exclude an existing linked leave request."))
        return super().write(values)

    def unlink(self):
        self._ensure_manager()
        if any(record.state != "draft" or record._has_usage() for record in self):
            raise UserError(_("Used or active policies cannot be deleted. Retire or archive them instead."))
        return super().unlink()

    @api.constrains("annual_days", "date_from", "date_to", "version", "rounding_step",
                    "full_day_notice_days", "half_day_notice_days", "wfh_notice_days")
    def _check_values(self):
        nonnegative = ("annual_days", "rounding_step", "full_day_notice_days", "half_day_notice_days", "wfh_notice_days")
        for record in self:
            if record.date_to and record.date_to < record.date_from:
                raise ValidationError(_("Policy end date cannot precede its start date."))
            if any(not math.isfinite(record[field]) or record[field] < 0 for field in nonnegative):
                raise ValidationError(_("Policy quantities and notice periods must be finite and nonnegative."))
            if record.version < 1:
                raise ValidationError(_("A policy version must be positive."))

    def _validate_activation(self):
        self.ensure_one()
        if not self.annual_leave_type_id or not self.unpaid_leave_type_id:
            raise UserError(_("Configure paid and unpaid leave types before activating this policy."))
        if self.wfh_enabled and not self.wfh_leave_type_id:
            raise UserError(_("Configure a worked-time WFH type or disable Work From Home."))
        types = self.annual_leave_type_id | self.unpaid_leave_type_id | self.wfh_leave_type_id
        expected_count = bool(self.annual_leave_type_id) + bool(self.unpaid_leave_type_id) + bool(self.wfh_leave_type_id)
        if len(types) != expected_count:
            raise UserError(_("Paid leave, unpaid leave and Work From Home must use distinct types."))
        if any(not kind.active or kind.company_id and kind.company_id != self.company_id for kind in types):
            raise UserError(_("Each configured type must be active and compatible with the policy company."))
        annual = self.annual_leave_type_id
        if not annual.requires_allocation or annual.unpaid or annual.time_type != "leave":
            raise UserError(_("The paid type must require an allocation and be a paid absence type."))
        if annual.request_unit != self.request_unit or annual.include_public_holidays_in_duration != self.include_public_holidays:
            raise UserError(_("The paid leave type duration settings differ from the policy. Configure the types first."))
        if self.unpaid_leave_type_id.requires_allocation or not self.unpaid_leave_type_id.unpaid:
            raise UserError(_("The unpaid type must be unpaid and must not require allocation."))
        if self.wfh_leave_type_id and (self.wfh_leave_type_id.time_type != "other" or
                self.wfh_leave_type_id.unpaid or self.wfh_leave_type_id.requires_allocation):
            raise UserError(_("Work From Home must be paid worked time without an allocation requirement."))
        if self.exception_mode != "disabled" and not self.management_user_ids:
            raise UserError(_("Select Management Exception Approvers, or disable policy exceptions."))
        for role_name, users in ((_("HR"), self.hr_user_ids), (_("Management"), self.management_user_ids)):
            if any(not user.active or user.share or self.company_id not in user.company_ids for user in users):
                raise UserError(_("Configured approvers must be active internal users with access to the policy company."))
            if any(not user.has_group("hr_holidays.group_hr_holidays_user") for user in users):
                raise UserError(_("%s approvers need Time Off Officer or Administrator access. Assign the native access explicitly.", role_name))

    def action_activate(self):
        self._ensure_manager()
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only draft policies can be activated."))
            record._validate_activation()
        return super(DvzLeavePolicy, self).write({"state": "active"})

    def action_retire(self):
        self._ensure_manager()
        return super(DvzLeavePolicy, self).write({"state": "retired"})

    def action_revision(self):
        self.ensure_one()
        self._ensure_manager()
        revision = self.copy({"name": _("%s / Revision %s", self.name, self.version + 1),
            "state": "draft", "version": self.version + 1, "active": True,
            "date_from": max(fields.Date.context_today(self), self.date_from), "date_to": False})
        return {"type": "ir.actions.act_window", "name": _("Policy Revision"),
                "res_model": self._name, "res_id": revision.id, "view_mode": "form", "target": "current"}

    def _get_period(self, as_of_date):
        self.ensure_one()
        return policy_engine.year_period(as_of_date)

    @api.model
    def _get_for_employee(self, employee, on_date):
        employee.ensure_one()
        day = fields.Date.to_date(on_date)
        if not day:
            raise UserError(_("A request date is required to select the assigned leave policy."))
        employee = employee.sudo()
        assigned = employee.dvz_leave_policy_id.sudo()
        if not assigned:
            return self.browse()
        if assigned.company_id != employee.company_id:
            raise UserError(_("The employee's policy belongs to a different company."))
        if assigned.active and assigned.state == "active" and assigned.date_from <= day and (
                not assigned.date_to or assigned.date_to >= day):
            return assigned
        raise UserError(_("The employee's assigned policy is not active for this date. Review the assignment or effective dates."))

    def _employee_eligibility(self, employee, on_date):
        self.ensure_one()
        employee.ensure_one()
        if employee.company_id != self.company_id:
            raise UserError(_("The employee and policy must belong to the same company."))
        employee = employee.sudo()
        person = {"joining_date": employee.dvz_joining_date, "status": employee.dvz_employment_status,
            "first_paid_date": employee.dvz_paid_eligible_date, "probation_end_date": employee.dvz_probation_end_date}
        try:
            return policy_engine.eligibility({"probation_end_inclusive": self.probation_end_inclusive}, person, on_date)
        except policy_engine.PolicyCalculationError as exc:
            raise UserError(str(exc)) from None

    def _calculation_options(self):
        self.ensure_one()
        return {"basis": self.proration_basis, "rounding_step": self.rounding_step, "rounding_method": self.rounding_method}

    def _compute_entitlement(self, employee, year_start, year_end, as_of_date=None):
        self.ensure_one()
        info = self._employee_eligibility(employee, as_of_date or fields.Date.context_today(self))
        if not info["eligible"]:
            return 0.0
        try:
            return float(policy_engine.entitlement_days(self.annual_days, year_start, year_end,
                info["joining_date"], info["first_paid_date"], **self._calculation_options()))
        except policy_engine.PolicyCalculationError as exc:
            raise UserError(str(exc)) from None

    def _approval_users(self, employee, role):
        self.ensure_one()
        employee.ensure_one()
        employee = employee.sudo()
        if role == "hod":
            users = employee.leave_manager_id
        elif role == "hr":
            users = self.hr_user_ids.sudo()
            if not users:
                group = self.env.ref("hr_holidays.group_hr_holidays_manager")
                users = self.env["res.users"].sudo().search([("active", "=", True), ("share", "=", False),
                    ("company_ids", "in", employee.company_id.id), ("all_group_ids", "in", group.id)])
        elif role == "management":
            users = self.management_user_ids.sudo()
        else:
            raise UserError(_("Unknown approval role."))
        return users.filtered(lambda user: user.active and not user.share and employee.company_id in user.company_ids)

    def _validate_approvers_for_employee(self, employee, roles):
        """Validate the fixed native HOD route without granting any access."""
        self.ensure_one()
        employee.ensure_one()
        employee = employee.sudo()
        if employee.company_id != self.company_id:
            raise UserError(_("The approval policy and employee must belong to the same company."))
        names = {"hod": _("HOD"), "hr": _("HR"), "management": _("Management")}
        effective_users = {}
        for role in dict.fromkeys(roles):
            if role not in names:
                raise UserError(_("Unknown approval role."))
            users = self.sudo()._approval_users(employee, role)
            if not users:
                raise UserError(_("No active %s approver with access to the employee's company is configured.", names[role]))
            users -= employee.user_id
            if not users:
                raise UserError(_("No eligible %s approver remains because self-approval is not permitted.", names[role]))
            effective_users[role] = users
            for user in users:
                officer = user.has_group("hr_holidays.group_hr_holidays_user")
                native_hod = (role == "hod" and user == employee.leave_manager_id and
                              user.has_group("hr_holidays.group_hr_holidays_responsible"))
                if not (officer or native_hod):
                    raise UserError(_("%s (%s approver) cannot access this employee's Time Off requests. Set the native Time Off approver for HOD; HR and Management require Officer/Administrator access.",
                        user.display_name, names[role]))
        if ("hod" in effective_users and "hr" in effective_users and
                not any(hod.id != hr.id for hod in effective_users["hod"] for hr in effective_users["hr"])):
            raise UserError(_("HOD and HR approvals require two different eligible users. Assign an additional approver."))
        return True

