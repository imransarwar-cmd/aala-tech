"""One explicit default for automatic assignment to newly created employees."""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    dvz_default_leave_policy_id = fields.Many2one(
        "dvz.leave.policy", string="Leave Policy for New Employees", copy=False,
        check_company=True, ondelete="restrict",
        help="Selected from an active policy's Use for New Employees action. Only newly created employees receive it; no eligibility or allocation is granted.")

    def _dvz_check_default_configuration_access(self, values):
        if "dvz_default_leave_policy_id" in values and not self.env.su and not (
                self.env.user.has_group("hr.group_hr_manager") or
                self.env.user.has_group("hr_holidays.group_hr_holidays_manager")):
            raise AccessError(_("Only HR or Time Off administrators can choose the policy for new employees."))

    @api.model_create_multi
    def create(self, vals_list):
        if "default_dvz_default_leave_policy_id" in self.env.context:
            self._dvz_check_default_configuration_access({"dvz_default_leave_policy_id": True})
        for values in vals_list:
            self._dvz_check_default_configuration_access(values)
        return super().create(vals_list)

    def write(self, values):
        self._dvz_check_default_configuration_access(values)
        return super().write(values)

    @api.constrains("dvz_default_leave_policy_id")
    def _check_dvz_default_leave_policy(self):
        for company in self:
            policy = company.dvz_default_leave_policy_id
            if not policy:
                continue
            self.env.cr.execute("SELECT id FROM dvz_leave_policy WHERE id = %s FOR SHARE", [policy.id])
            policy.invalidate_recordset(["company_id", "active", "state"])
            if policy.company_id != company or not policy.active or policy.state != "active":
                raise ValidationError(_("The policy for new employees must be active and belong to this company."))
            policy._validate_activation()
