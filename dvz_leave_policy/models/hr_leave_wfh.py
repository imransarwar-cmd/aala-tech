"""WFH commitments and delivery of completed-task updates to HOD and HR."""
import hashlib

from markupsafe import Markup, escape

from odoo import api, Command, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


_UPDATE_AUDIT_FIELDS = frozenset({
    "dvz_task_update_sent_at", "dvz_task_update_sent_by", "dvz_task_update_recipient_ids",
    "dvz_task_update_message_id", "dvz_task_update_sent_digest", "dvz_task_update_completed",
})


def update_digest(text):
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


class HrLeaveWfh(models.Model):
    _inherit = "hr.leave"

    dvz_wfh_available = fields.Boolean(string="Available During Working Hours", tracking=True)
    dvz_wfh_communication = fields.Boolean(string="Maintain Team Communication", tracking=True)
    dvz_task_update_sent_at = fields.Datetime(string="Last Task Update Sent", readonly=True, copy=False)
    dvz_task_update_sent_by = fields.Many2one("res.users", string="Task Update Sent By", readonly=True, copy=False)
    dvz_task_update_recipient_ids = fields.Many2many("res.users", "dvz_leave_task_update_user_rel", "leave_id", "user_id",
        string="Last Task Update Recipients", readonly=True, copy=False)
    dvz_task_update_message_id = fields.Many2one("mail.message", string="Last Task Update Notification",
        readonly=True, copy=False, ondelete="set null")
    dvz_task_update_sent_digest = fields.Char(readonly=True, copy=False)
    dvz_task_update_completed = fields.Boolean(string="Task Update Sent to HOD and HR",
        compute="_compute_dvz_task_update_completion", store=True)

    def _dvz_request_field_names(self):
        return super()._dvz_request_field_names() | {"dvz_wfh_available", "dvz_wfh_communication"}

    @api.model_create_multi
    def create(self, vals_list):
        if any("default_" + name in self.env.context for name in _UPDATE_AUDIT_FIELDS):
            raise AccessError(_("Task update delivery evidence cannot be supplied as creation defaults."))
        if not self._dvz_is_internal() and any(_UPDATE_AUDIT_FIELDS.intersection(values) for values in vals_list):
            raise AccessError(_("Task update evidence is recorded only by the checked submission action."))
        return super().create(vals_list)

    def write(self, values):
        internal = self._dvz_is_internal()
        if not internal and _UPDATE_AUDIT_FIELDS.intersection(values):
            raise AccessError(_("Task update delivery evidence cannot be edited directly."))
        changed = bool(set(values) & self._dvz_request_field_names())
        result = super().write(values)
        if not internal and changed:
            # Retain who received the previous message, but it cannot prove
            # completion for a changed employee, period or set of commitments.
            self.filtered(lambda leave: leave.dvz_kind == "wfh")._dvz_internal().write({
                "dvz_task_update_sent_digest": False})
        return result

    def _dvz_validate_policy(self, final=False):
        result = super()._dvz_validate_policy(final=final)
        for leave in self.filtered(lambda item: item.dvz_kind == "wfh"):
            policy, employee = leave.dvz_policy_id.sudo(), leave.employee_id.sudo()
            if policy.wfh_availability_required and not leave.dvz_wfh_available:
                raise ValidationError(_("Confirm availability during working hours before submitting WFH."))
            if policy.wfh_communication_required and not leave.dvz_wfh_communication:
                raise ValidationError(_("Confirm that team communication will be maintained during WFH."))
            if not leave._dvz_exception_valid(final=final):
                eligibility = policy._employee_eligibility(employee, leave.request_date_from)
                if not eligibility["eligible"]:
                    raise ValidationError(_("WFH is not available under the employee's policy eligibility: %s.",
                        eligibility["reason"]))
        return result

    def _dvz_task_update_complete(self):
        self.ensure_one()
        return bool(
            super()._dvz_task_update_complete() and self.dvz_task_update_sent_at and
            self.dvz_task_update_sent_by and self.dvz_task_update_recipient_ids and
            self.dvz_task_update_message_id and
            self.dvz_task_update_sent_digest == update_digest(self.dvz_task_update) and
            self.date_from and self.dvz_task_update_sent_at >= self.date_from)

    @api.depends("dvz_kind", "dvz_task_update", "dvz_task_update_sent_at", "dvz_task_update_sent_by",
        "dvz_task_update_recipient_ids", "dvz_task_update_message_id", "dvz_task_update_sent_digest", "date_from")
    def _compute_dvz_task_update_completion(self):
        for leave in self:
            leave.dvz_task_update_completed = leave.dvz_kind == "wfh" and leave._dvz_task_update_complete()

    def _dvz_check_task_update_actor(self):
        self.ensure_one()
        self.check_access("read")
        employee, policy = self.employee_id.sudo(), self.dvz_policy_id.sudo()
        if self.dvz_kind != "wfh" or not policy or self.state not in ("confirm", "validate1", "validate"):
            raise UserError(_("Task updates can be submitted only for an active WFH request."))
        if employee.company_id not in self.env.companies:
            raise AccessError(_("Select the request's allowed company before submitting its task update."))
        users = employee.user_id | policy._approval_users(employee, "hod") | policy._approval_users(employee, "hr")
        if self.env.uid not in users.ids:
            raise AccessError(_("Only the employee or the configured HOD/HR approvers can submit this task update."))

    def action_dvz_open_task_update(self):
        self.ensure_one()
        self._dvz_check_task_update_actor()
        return {"type": "ir.actions.act_window", "name": _("WFH Task Update"),
            "res_model": "dvz.wfh.update.wizard", "view_mode": "form", "target": "new",
            "context": {"default_leave_id": self.id, "default_task_update": self.dvz_task_update or ""}}

    def action_dvz_send_task_update(self, update_text=None):
        self.ensure_one()
        return self._dvz_store_task_update(self.dvz_task_update if update_text is None else update_text, send=True)

    def action_dvz_save_task_update(self, update_text=None):
        self.ensure_one()
        return self._dvz_store_task_update(self.dvz_task_update if update_text is None else update_text, send=False)

    def _dvz_store_task_update(self, update_text, send):
        self.ensure_one()
        self._dvz_check_task_update_actor()
        if not isinstance(update_text, str) or not update_text.strip():
            raise ValidationError(_("Enter a nonempty task update."))
        actor = self.env.user
        self.env.cr.execute("SELECT id FROM hr_leave WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset()
        self._dvz_check_task_update_actor()
        policy, employee = self.dvz_policy_id.sudo(), self.employee_id.sudo()
        values = {"dvz_task_update": update_text.strip()}
        recipients = self.env["res.users"].sudo()
        if send:
            if not self.date_from or fields.Datetime.now() < self.date_from:
                raise UserError(_("Completed-task updates can be sent after the WFH period has started. Save a draft before then."))
            for role in ("hod", "hr"):
                users = policy._approval_users(employee, role)
                if not users:
                    raise UserError(_("No active %s recipient is configured for this task update.", role.upper()))
                if any(not self.with_user(user).with_context(
                        allowed_company_ids=employee.company_id.ids).has_access("read") for user in users):
                    raise UserError(_("A task-update recipient cannot read this request. Review their Time Off access."))
                recipients |= users
        # Explicit owner/role/read/company checks above bound this privileged
        # write to task text and proof. Actor, recipients and fields are not
        # accepted from RPC callers.
        target = self.sudo()._dvz_internal()
        if send:
            body = Markup("<p>%s</p><pre>%s</pre>") % (
                escape(_("WFH task update for %s", employee.display_name)), escape(update_text.strip()))
            message = target.message_notify(body=body, subject=_("WFH task update"),
                author_id=actor.partner_id.id, partner_ids=recipients.partner_id.ids)
            values.update({"dvz_task_update_sent_at": fields.Datetime.now(), "dvz_task_update_sent_by": actor.id,
                "dvz_task_update_recipient_ids": [Command.set(recipients.ids)],
                "dvz_task_update_message_id": message.id, "dvz_task_update_sent_digest": update_digest(update_text)})
        target.write(values)
        return {"type": "ir.actions.act_window_close"}

