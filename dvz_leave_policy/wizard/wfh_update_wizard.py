from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DvzWfhUpdateWizard(models.TransientModel):
    _name = "dvz.wfh.update.wizard"
    _description = "Submit WFH Task Update"

    leave_id = fields.Many2one("hr.leave", string="WFH Request", required=True, readonly=True)
    task_update = fields.Text(string="Task Update", required=True)

    @api.constrains("leave_id")
    def _check_leave(self):
        for wizard in self:
            wizard.leave_id._dvz_check_task_update_actor()

    def action_send(self):
        self.ensure_one()
        if not (self.task_update or "").strip():
            raise ValidationError(_("Enter a task update before sending."))
        return self.leave_id.action_dvz_send_task_update(self.task_update)

    def action_save(self):
        self.ensure_one()
        return self.leave_id.action_dvz_save_task_update(self.task_update)

