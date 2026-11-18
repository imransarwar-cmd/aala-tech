from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


_CONFIGURATION_FIELDS = frozenset({
    "dvz_leave_policy_id", "dvz_employment_status", "dvz_joining_date",
    "dvz_paid_eligible_date", "dvz_probation_end_date",
})


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    dvz_leave_policy_id = fields.Many2one("dvz.leave.policy", string="Leave Policy", check_company=True,
        help="Only this explicitly assigned employee uses the policy; there is no company-wide default.")
    dvz_employment_status = fields.Selection([
        ("unknown", "Not Confirmed"), ("permanent", "Permanent"),
        ("probation", "Probation"), ("temporary", "Temporary")],
        string="Leave Eligibility Status", default="unknown", tracking=True)
    dvz_joining_date = fields.Date(string="Joining Date for Leave", tracking=True)
    dvz_paid_eligible_date = fields.Date(string="First Paid Leave Date", tracking=True,
        help="Verified first day of paid-leave eligibility. Takes priority over a probation end date.")
    dvz_probation_end_date = fields.Date(string="Probation End Date", tracking=True,
        help="Use a verified date. The policy controls whether eligibility starts on this date or the next day; no probation duration is assumed.")

    def _dvz_check_configuration_access(self, values):
        if _CONFIGURATION_FIELDS.intersection(values) and not self.env.su and not (
            self.env.user.has_group("hr.group_hr_manager") or
            self.env.user.has_group("hr_holidays.group_hr_holidays_manager")
        ):
            raise AccessError(_("Only HR or Time Off administrators can change leave-policy eligibility."))

    @api.model_create_multi
    def create(self, vals_list):
        context_fields = {name for name in _CONFIGURATION_FIELDS if "default_" + name in self.env.context}
        self._dvz_check_configuration_access(context_fields)
        for values in vals_list:
            self._dvz_check_configuration_access(values)
        return super().create(vals_list)

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

