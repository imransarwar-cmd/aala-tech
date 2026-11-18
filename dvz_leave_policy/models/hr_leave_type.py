from odoo import models, _
from odoo.exceptions import UserError, ValidationError


_DURATION_FIELDS = {'request_unit', 'include_public_holidays_in_duration', 'requires_allocation',
                    'unpaid', 'time_type', 'allows_negative', 'max_allowed_negative'}


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    def write(self, vals):
        sensitive = _DURATION_FIELDS | {'leave_validation_type', 'allocation_validation_type', 'company_id'}
        if set(vals) & sensitive:
            for leave_type in self:
                changed = {k for k in set(vals) & sensitive if leave_type[k] != vals[k]}
                if not changed:
                    continue
                managed_use = self.env['hr.leave'].sudo().search_count([
                    ('holiday_status_id', '=', leave_type.id), ('dvz_policy_id', '!=', False)], limit=1)
                managed_use += self.env['hr.leave.allocation'].sudo().search_count([
                    ('holiday_status_id', '=', leave_type.id), ('dvz_policy_id', '!=', False)], limit=1)
                active_policy = self.env['dvz.leave.policy'].sudo().search_count([
                    ('state', 'in', ['active', 'retired']), '|', '|',
                    ('annual_leave_type_id', '=', leave_type.id),
                    ('unpaid_leave_type_id', '=', leave_type.id),
                    ('wfh_leave_type_id', '=', leave_type.id)], limit=1)
                if managed_use or active_policy:
                    raise UserError(_('This type has policy-controlled records. Create a new type for changed duration, balance or native validation rules, and select it on a policy revision.'))
        return super().write(vals)


class DvzLeavePolicyTypeConfiguration(models.Model):
    _inherit = 'dvz.leave.policy'

    def _type_settings(self, kind):
        self.ensure_one()
        return {
            'requires_allocation': kind == 'paid', 'employee_requests': False,
            'request_unit': self.request_unit, 'unpaid': kind == 'unpaid',
            'time_type': 'other' if kind == 'wfh' else 'leave',
            'include_public_holidays_in_duration': self.include_public_holidays,
            # Full and half working days share the same balance. The policy
            # request records the actual HOD and HR approvals.
            'leave_validation_type': 'both', 'allocation_validation_type': 'hr',
            'allows_negative': False, 'max_allowed_negative': 0,
        }

    def action_configure_types(self):
        self._ensure_manager()
        for policy in self:
            if policy.state != 'draft' or policy._has_usage():
                raise UserError(_('Configure types on an unused draft policy or a new revision.'))
            for kind, field, label in (
                ('paid', 'annual_leave_type_id', _('Paid Leave')),
                ('unpaid', 'unpaid_leave_type_id', _('Unpaid Leave')),
                ('wfh', 'wfh_leave_type_id', _('Work From Home')),
            ):
                if kind == 'wfh' and not policy.wfh_enabled:
                    continue
                leave_type = policy[field]
                desired = policy._type_settings(kind)
                if leave_type:
                    if leave_type.company_id != policy.company_id:
                        raise UserError(_('Select a type belonging to the policy company. Shared types must be reviewed and configured separately.'))
                    changed = {k: v for k, v in desired.items() if leave_type[k] != v}
                    if changed:
                        used = self.env['hr.leave'].sudo().search_count([('holiday_status_id', '=', leave_type.id)], limit=1)
                        used += self.env['hr.leave.allocation'].sudo().search_count([('holiday_status_id', '=', leave_type.id)], limit=1)
                        if used and set(changed) & _DURATION_FIELDS:
                            raise UserError(_('Changing this used type could recalculate prior records. Select a new type on this policy revision.'))
                        leave_type.write(changed)
                else:
                    # Do not silently create a second paid balance when one already exists.
                    if kind == 'paid' and self.env['hr.leave.type'].search_count([
                        ('company_id', 'in', [False, policy.company_id.id]), ('unpaid', '=', False),
                        ('requires_allocation', '=', True)], limit=1):
                        raise UserError(_('Paid allocation types already exist. Select the intended type, or create and select a new one explicitly for the revision.'))
                    leave_type = self.env['hr.leave.type'].create({**desired, 'name': '%s - %s' % (policy.name, label), 'company_id': policy.company_id.id})
                    policy[field] = leave_type
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Leave Types Configured'), 'message': _('Review approvers and effective dates, then activate the policy.'), 'type': 'success', 'sticky': False}}

    def _validate_activation(self):
        super()._validate_activation()
        for kind, leave_type in (('paid', self.annual_leave_type_id), ('unpaid', self.unpaid_leave_type_id), ('wfh', self.wfh_leave_type_id)):
            if not leave_type:
                continue
            settings = self._type_settings(kind)
            if any(leave_type[k] != v for k, v in settings.items()):
                raise ValidationError(_('The %s type does not match the selected policy settings. Configure the types before activation.', kind))
