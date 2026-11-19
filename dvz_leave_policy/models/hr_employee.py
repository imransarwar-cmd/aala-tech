from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


_CONFIGURATION_FIELDS = frozenset({
    "dvz_leave_policy_id", "dvz_employment_status", "dvz_joining_date",
    "dvz_paid_eligible_date", "dvz_probation_end_date",
})


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    dvz_leave_policy_id = fields.Many2one("dvz.leave.policy", string="Leave Policy", check_company=True, copy=False,
        help="New employees receive their company's configured default policy when saved. Assignment does not grant paid leave or require eligibility dates.")
    dvz_employment_status = fields.Selection([
        ("unknown", "Not Confirmed"), ("permanent", "Permanent"),
        ("probation", "Probation"), ("temporary", "Temporary")],
        string="Leave Eligibility Status", default="unknown", tracking=True, copy=False)
    dvz_joining_date = fields.Date(string="Joining Date for Leave", tracking=True, copy=False)
    dvz_paid_eligible_date = fields.Date(string="First Paid Leave Date", tracking=True, copy=False,
        help="Verified first day of paid-leave eligibility. Takes priority over a probation end date.")
    dvz_probation_end_date = fields.Date(string="Probation End Date", tracking=True, copy=False,
        help="Use a verified date. The policy controls whether eligibility starts on this date or the next day; no probation duration is assumed.")

    def _dvz_check_configuration_access(self, values):
        if _CONFIGURATION_FIELDS.intersection(values) and not self.env.su and not (
            self.env.user.has_group("hr.group_hr_manager") or
            self.env.user.has_group("hr_holidays.group_hr_holidays_manager")
        ):
            raise AccessError(_("Only HR or Time Off administrators can change leave-policy eligibility."))

    @api.model_create_multi
    def create(self, vals_list):
        # Check caller-supplied values before inserting the administrator's company
        # default. Native create permissions and record/company rules still apply.
        context_fields = {name for name in _CONFIGURATION_FIELDS if "default_" + name in self.env.context}
        self._dvz_check_configuration_access(context_fields)
        for values in vals_list:
            self._dvz_check_configuration_access(values)
        company_default = self.default_get(["company_id"]).get("company_id") or self.env.company.id
        clean = []
        for values in vals_list:
            values = dict(values)
            values.setdefault("company_id", company_default)
            company_id = values.get("company_id", company_default)
            company = self.env["res.company"].browse(company_id).exists()
            if company and company not in self.env.companies and not self.env.su:
                raise AccessError(_("Select an employee company from your allowed companies."))
            # An empty policy sent by a form/import means use the company default.
            # A deliberate nonempty assignment remains an administrator decision.
            chosen = values.get("dvz_leave_policy_id")
            if "dvz_leave_policy_id" not in values:
                chosen = self.env.context.get("default_dvz_leave_policy_id")
            if not chosen:
                policy = company.dvz_default_leave_policy_id if company else self.env["dvz.leave.policy"]
                if policy and (policy.company_id != company or not policy.active or policy.state != "active"):
                    raise UserError(_("The company's policy for new employees is unavailable. An administrator must select an active policy or stop automatic assignment."))
                # Effective dates are checked when leave/allocation is requested;
                # an employee can be created before the policy starts.
                values["dvz_leave_policy_id"] = policy.id or False
            clean.append(values)
        return super().create(clean)

    def copy_data(self, default=None):
        values_list = super().copy_data(default=default)
        if "leave_manager_id" not in (default or {}):
            for values in values_list:
                # A copied employee needs their own confirmed approval route.
                values["leave_manager_id"] = False
        return values_list

    def write(self, values):
        self._dvz_check_configuration_access(values)
        return super().write(values)

    @api.constrains("dvz_joining_date", "dvz_paid_eligible_date", "dvz_probation_end_date", "dvz_leave_policy_id", "company_id")
    def _check_dvz_configuration(self):
        for employee in self:
            if employee.dvz_leave_policy_id and employee.dvz_leave_policy_id.company_id != employee.company_id:
                raise ValidationError(_("The employee and assigned leave policy must belong to the same company."))
            for day in (employee.dvz_paid_eligible_date, employee.dvz_probation_end_date):
                if day and employee.dvz_joining_date and day < employee.dvz_joining_date:
                    raise ValidationError(_("Paid eligibility and probation dates cannot precede the joining date."))

