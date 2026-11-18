from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class DvzLeaveAllocationWizard(models.TransientModel):
    _name = "dvz.leave.allocation.wizard"
    _description = "Employee Annual Allocation"

    policy_id = fields.Many2one("dvz.leave.policy", required=True, domain=[("state", "=", "active")])
    employee_id = fields.Many2one("hr.employee", string="Employee", required=True)
    as_of_date = fields.Date(string="Calculation Date", required=True, default=fields.Date.context_today)
    approve = fields.Boolean(string="Approve Using My Native Access Rights", default=False)
    line_ids = fields.One2many("dvz.leave.allocation.wizard.line", "wizard_id", string="Annual Preview", readonly=True)

    def _require_manager(self):
        self.env["hr.leave.allocation"]._dvz_require_manager()

    @api.model_create_multi
    def create(self, vals_list):
        self._require_manager()
        return super().create(vals_list)

    def write(self, values):
        self._require_manager()
        if {"policy_id", "as_of_date", "employee_id"}.intersection(values):
            self.line_ids.unlink()
        return super().write(values)

    def _collect_proposal(self):
        self.ensure_one()
        self._require_manager()
        if not self.employee_id:
            raise UserError(_("Select exactly one existing employee."))
        if self.policy_id.company_id not in self.env.companies:
            raise UserError(_("The policy company is outside your allowed companies."))
        try:
            return self.policy_id._allocation_values_for_employee(self.employee_id, self.as_of_date)
        except (UserError, ValidationError, AccessError) as exc:
            start, end = self.policy_id._get_period(self.as_of_date)
            return {"employee_id": self.employee_id.id, "period_start": start, "period_end": end,
                "days": 0.0, "status": "error", "message": str(exc), "allocation_id": False, "values": {}}

    def _store_preview(self, proposal):
        self.line_ids.unlink()
        self.env["dvz.leave.allocation.wizard.line"].create({
            "wizard_id": self.id, **{name: proposal[name] for name in (
                "employee_id", "period_start", "period_end", "days", "status", "message")}})

    def action_preview(self):
        self.ensure_one()
        self._store_preview(self._collect_proposal())
        return {"type": "ir.actions.act_window", "name": _("Employee Annual Allocation"),
            "res_model": self._name, "res_id": self.id, "view_mode": "form", "target": "new"}

    def action_generate(self):
        self.ensure_one()
        self._require_manager()
        if not self.employee_id:
            raise UserError(_("Select exactly one existing employee."))
        allocation = self.policy_id._create_allocation_for_employee(
            self.employee_id, self.as_of_date, approve=self.approve)
        self._store_preview(self._collect_proposal())
        if not allocation:
            return {"type": "ir.actions.act_window", "name": _("Employee Annual Allocation"),
                "res_model": self._name, "res_id": self.id, "view_mode": "form", "target": "new"}
        return {"type": "ir.actions.act_window", "name": _("Annual Allocation"),
            "res_model": "hr.leave.allocation", "view_mode": "form", "res_id": allocation.id, "target": "current"}


class DvzLeaveAllocationWizardLine(models.TransientModel):
    _name = "dvz.leave.allocation.wizard.line"
    _description = "Employee Annual Allocation Preview"
    _order = "id"

    wizard_id = fields.Many2one("dvz.leave.allocation.wizard", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, readonly=True)
    period_start = fields.Date(readonly=True)
    period_end = fields.Date(readonly=True)
    days = fields.Float(readonly=True, digits=(16, 4))
    status = fields.Selection([("create", "Ready"), ("reuse", "Already Exists"),
        ("skip", "No Grant Due"), ("error", "Review Required")], readonly=True)
    message = fields.Text(readonly=True)

