"""Generic preset for the supplied leave policy, with one-employee setup."""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


DOCUMENT_POLICY_VALUES = {
    "name": "Leave and Absence Policy",
    "active": True,
    "state": "draft",
    "source_based": True,
    "source_revision_date": "2025-03-10",
    "configuration_reviewed": False,
    "annual_days": 24.0,
    "proration_basis": "joining",
    "rounding_step": 0.5,
    "rounding_method": "down",
    "probation_end_inclusive": True,
    "request_unit": "half_day",
    "include_public_holidays": False,
    "approval_mode": "both",
    "unpaid_approval_mode": "hr",
    "wfh_approval_mode": "both",
    "full_day_notice_days": 0,
    "half_day_notice_days": 1,
    "require_prior_approval": True,
    "allow_emergency": True,
    "emergency_waives_notice": True,
    "exception_mode": "all_three",
    "half_day_return_action": "full_day",
    "unauthorized_action": "unpaid",
    "wfh_enabled": True,
    "wfh_notice_days": 0,
    "wfh_require_prior_approval": True,
    "wfh_unapproved_action": "unpaid",
    "wfh_task_update_required": True,
    "wfh_availability_required": True,
    "wfh_communication_required": True,
}

SOURCE_REVIEW_CHECKLIST = """
<p>Source revision: 10 March 2025. Choose the actual effective dates separately.</p>
<p>The source specifies 24 working days per calendar year, prorating new joiners,
HOD and HR approval, one day's half-day notice, unpaid actual unauthorized absence,
WFH responsibilities, Management exceptions, and year-end encashment.</p>
<p>Review the selected employee, verified joining and paid-eligibility dates,
actual approvers and leave types. The document does not specify the exact
proration formula, rounding, full-day/WFH notice duration or encashment rate.
Actual-day proration with joining-date basis and downward half-day rounding is
an editable implementation choice. Enter an approved rate on the year-end
settlement; no salary rate or payroll posting is inferred.</p>
"""


class DvzLeavePolicyPreset(models.Model):
    _inherit = "dvz.leave.policy"

    source_based = fields.Boolean(string="Based on Supplied Policy", default=False, copy=True)
    source_revision_date = fields.Date(string="Source Revision Date", copy=True,
        help="Informational document date. Effective From controls enforcement.")
    configuration_reviewed = fields.Boolean(string="Source Choices Reviewed", default=False,
        copy=False, tracking=True)
    source_review_checklist = fields.Html(string="Source Review", compute="_compute_source_review_checklist")

    @api.depends("source_based")
    def _compute_source_review_checklist(self):
        for policy in self:
            policy.source_review_checklist = SOURCE_REVIEW_CHECKLIST if policy.source_based else False

    @api.model
    def _document_preset_values(self):
        values = dict(DOCUMENT_POLICY_VALUES)
        values.update({"hr_user_ids": [fields.Command.clear()],
            "management_user_ids": [fields.Command.clear()], "notes": SOURCE_REVIEW_CHECKLIST})
        return values

    def _validate_activation(self):
        super()._validate_activation()
        if self.source_based and not self.configuration_reviewed:
            raise UserError(_("Review the source choices before activating this policy."))
        hr_required = (self.approval_mode in ("hr", "both") or self.unpaid_approval_mode in ("hr", "both")
            or self.wfh_enabled and self.wfh_approval_mode in ("hr", "both")
            or self.exception_mode == "all_three" or self.wfh_enabled and self.wfh_task_update_required)
        if self.source_based and hr_required and not self.hr_user_ids:
            raise UserError(_("Select the actual HR approver before activating the source policy."))

    def action_open_setup(self):
        self.ensure_one()
        self._ensure_manager()
        if self.state not in ("draft", "active"):
            raise UserError(_("Use an active policy or an unused draft to set up one employee."))
        context = {"default_company_id": self.company_id.id, "default_policy_id": self.id}
        if self.env.context.get("default_employee_id"):
            context["default_employee_id"] = self.env.context["default_employee_id"]
        return {"type": "ir.actions.act_window", "name": _("Set Up One Employee"),
            "res_model": "dvz.policy.setup.wizard", "view_mode": "form", "target": "new", "context": context}


class HrEmployeePolicySetup(models.Model):
    _inherit = "hr.employee"

    def action_dvz_open_policy_setup(self):
        self.ensure_one()
        self.check_access("read")
        if not self.env.su and not self.env.user.has_group("hr_holidays.group_hr_holidays_manager"):
            raise AccessError(_("Only a Time Off administrator can set up an employee's leave policy."))
        if self.company_id not in self.env.companies:
            raise AccessError(_("Select the employee's company among your allowed companies."))
        context = {"default_company_id": self.company_id.id, "default_employee_id": self.id}
        if self.dvz_leave_policy_id and self.dvz_leave_policy_id.state in ("draft", "active"):
            context["default_policy_id"] = self.dvz_leave_policy_id.id
        return {"type": "ir.actions.act_window", "name": _("Set Up One Employee"),
            "res_model": "dvz.policy.setup.wizard", "view_mode": "form", "target": "new", "context": context}
