"""Operational company default, separate from immutable policy rule versions."""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class DvzLeavePolicyAssignment(models.Model):
    _inherit = "dvz.leave.policy"

    is_employee_default = fields.Boolean(
        string="Assign to New Employees", compute="_compute_is_employee_default",
        help="This company's newly created employees receive this policy. Joining, probation and paid eligibility may be confirmed later; paid leave remains subject to those checks.")

    @api.depends("company_id.dvz_default_leave_policy_id")
    def _compute_is_employee_default(self):
        for policy in self:
            policy.is_employee_default = policy.company_id.dvz_default_leave_policy_id == policy

    def _dvz_lock_default_company(self):
        self.ensure_one()
        self._ensure_manager()
        self.check_access("write")
        if self.company_id not in self.env.companies:
            raise AccessError(_("Select the policy's company among your allowed companies."))
        company = self.company_id
        self.env.cr.execute("SELECT id FROM res_company WHERE id = %s FOR UPDATE", [company.id])
        company.invalidate_recordset(["dvz_default_leave_policy_id"])
        self.env.cr.execute("SELECT id FROM dvz_leave_policy WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["active", "state"])
        return company

    def action_use_for_new_employees(self):
        company = self._dvz_lock_default_company()
        if not self.active or self.state != "active":
            raise UserError(_("Activate and review this policy before using it for new employees."))
        self._validate_activation()
        # Company configuration normally requires Settings access. This narrowly
        # scoped write follows policy-manager, policy-access and company checks.
        company.sudo().write({"dvz_default_leave_policy_id": self.id})
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_stop_automatic_assignment(self):
        company = self._dvz_lock_default_company()
        if company.dvz_default_leave_policy_id == self:
            company.sudo().write({"dvz_default_leave_policy_id": False})
        return {"type": "ir.actions.client", "tag": "reload"}

    def _dvz_require_default_replacement(self):
        self._ensure_manager()
        self.check_access("write")
        companies = self.company_id.sorted("id")
        if not self.env.su and any(company not in self.env.companies for company in companies):
            raise AccessError(_("Select each policy's company among your allowed companies."))
        for company in companies:
            self.env.cr.execute("SELECT id FROM res_company WHERE id = %s FOR UPDATE", [company.id])
        companies.invalidate_recordset(["dvz_default_leave_policy_id"])
        for policy in self:
            if policy.company_id.dvz_default_leave_policy_id == policy:
                raise UserError(_("Select another policy for new employees or stop automatic assignment before retiring or archiving this policy. Existing employee assignments will remain unchanged."))

    def action_retire(self):
        self._dvz_require_default_replacement()
        return super().action_retire()

    def write(self, values):
        if values.get("active") is False:
            self._dvz_require_default_replacement()
        return super().write(values)
