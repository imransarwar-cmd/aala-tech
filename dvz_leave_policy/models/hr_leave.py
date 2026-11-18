from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


# A JSON/RPC caller cannot manufacture this object identity to bypass the guard.
_INTERNAL = object()
_AUDIT_FIELDS = {
    'dvz_policy_id', 'dvz_policy_version', 'dvz_hod_approved_by', 'dvz_hod_approved_at',
    'dvz_hr_approved_by', 'dvz_hr_approved_at', 'dvz_management_approved_by',
    'dvz_management_approved_at', 'dvz_return_review', 'dvz_violation_reason',
    'dvz_original_type_id',
    'dvz_kind', 'dvz_submitted_at', 'dvz_expected_return',
    'dvz_can_hod_approve', 'dvz_can_hr_approve', 'dvz_can_management_approve',
}
_REQUEST_FIELDS = {
    'employee_id', 'holiday_status_id', 'request_date_from', 'request_date_to',
    'request_date_from_period', 'request_date_to_period', 'request_hour_from',
    'request_hour_to', 'dvz_emergency', 'dvz_exception_requested', 'dvz_exception_reason',
}
_NATIVE_COMPUTED_FIELDS = {
    'date_from', 'date_to', 'number_of_days', 'number_of_hours',
    'request_unit_half', 'request_unit_hours', 'resource_calendar_id',
    'first_approver_id', 'second_approver_id',
    'validation_type', 'leave_type_request_unit',
}
_NATIVE_SKIP_FLAGS = {'leave_fast_create', 'leave_skip_state_check', 'leave_skip_date_check'}


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    dvz_policy_id = fields.Many2one('dvz.leave.policy', string='Leave Policy', readonly=True, copy=False, index=True, ondelete='restrict')
    dvz_policy_version = fields.Integer(string='Policy Version', readonly=True, copy=False)
    dvz_submitted_at = fields.Datetime(string='Policy Submitted At', readonly=True, copy=False)
    dvz_kind = fields.Selection([('paid', 'Paid Leave'), ('unpaid', 'Unpaid Leave'), ('wfh', 'Work From Home')], compute='_compute_dvz_kind', store=True)
    dvz_hod_approved_by = fields.Many2one('res.users', string='HOD Approved By', readonly=True, copy=False, tracking=True)
    dvz_hod_approved_at = fields.Datetime(string='HOD Approved At', readonly=True, copy=False)
    dvz_hr_approved_by = fields.Many2one('res.users', string='HR Approved By', readonly=True, copy=False, tracking=True)
    dvz_hr_approved_at = fields.Datetime(string='HR Approved At', readonly=True, copy=False)
    dvz_management_approved_by = fields.Many2one('res.users', string='Management Approved By', readonly=True, copy=False, tracking=True)
    dvz_management_approved_at = fields.Datetime(string='Management Approved At', readonly=True, copy=False)
    dvz_emergency = fields.Boolean(string='Emergency', tracking=True)
    dvz_exception_requested = fields.Boolean(string='Request Policy Exception', tracking=True)
    dvz_exception_reason = fields.Text(string='Exception Reason', tracking=True)
    dvz_task_update = fields.Text(string='WFH Task Update', tracking=True)
    dvz_expected_return = fields.Datetime(string='Expected Return', compute='_compute_dvz_expected_return')
    dvz_return_review = fields.Boolean(string='Return Requires Review', readonly=True, copy=False, tracking=True)
    dvz_violation_reason = fields.Text(string='Policy Review', readonly=True, copy=False, tracking=True)
    dvz_original_type_id = fields.Many2one('hr.leave.type', string='Original Time Off Type', readonly=True, copy=False)
    dvz_return_reference = fields.Char(string='Verified Return Evidence', groups='hr_holidays.group_hr_holidays_manager', tracking=True)
    dvz_absence_reference = fields.Char(string='Verified Absence Evidence', groups='hr_holidays.group_hr_holidays_manager', tracking=True)
    dvz_can_hod_approve = fields.Boolean(compute='_compute_dvz_can_approve')
    dvz_can_hr_approve = fields.Boolean(compute='_compute_dvz_can_approve')
    dvz_can_management_approve = fields.Boolean(compute='_compute_dvz_can_approve')

    @api.depends('dvz_policy_id', 'holiday_status_id')
    def _compute_dvz_kind(self):
        for leave in self:
            policy = leave.dvz_policy_id
            leave.dvz_kind = ('paid' if leave.holiday_status_id == policy.annual_leave_type_id else
                              'unpaid' if leave.holiday_status_id == policy.unpaid_leave_type_id else
                              'wfh' if leave.holiday_status_id == policy.wfh_leave_type_id else False) if policy else False

    def _dvz_internal(self):
        return self.with_context(_dvz_policy_internal=_INTERNAL)

    def _dvz_is_internal(self):
        return self.env.context.get('_dvz_policy_internal') is _INTERNAL

    def _dvz_request_field_names(self):
        """Extension hook for inputs whose edits must restart approval."""
        return _REQUEST_FIELDS

    def _dvz_task_update_complete(self):
        self.ensure_one()
        return bool((self.dvz_task_update or '').strip())

    def _dvz_check_wfh_task_update_for_approval(self):
        self.ensure_one()
        if self.dvz_policy_id.wfh_task_update_required and self.date_to < fields.Datetime.now() and not self._dvz_task_update_complete():
            raise ValidationError(_('Enter the WFH task update before approving an already completed WFH period.'))

    @api.model
    def _dvz_policy_for_request(self, employee, leave_type, request_day):
        Policy = self.env['dvz.leave.policy'].sudo()
        if not employee or not leave_type:
            return Policy
        request_day = fields.Date.to_date(request_day)
        if not request_day:
            raise ValidationError(_('A request start date is required to select the applicable policy.'))
        assigned = employee.sudo().dvz_leave_policy_id
        if (assigned and (not assigned.date_to or assigned.date_to >= request_day)
                and leave_type not in (assigned.annual_leave_type_id | assigned.unpaid_leave_type_id | assigned.wfh_leave_type_id)):
            return Policy
        policy = Policy._get_for_employee(employee.sudo(), request_day)
        return policy if policy and leave_type in (
            policy.annual_leave_type_id | policy.unpaid_leave_type_id | policy.wfh_leave_type_id) else Policy

    def _dvz_mode(self):
        self.ensure_one()
        if self.dvz_kind == 'wfh':
            return self.dvz_policy_id.wfh_approval_mode
        if self.dvz_kind == 'unpaid':
            return self.dvz_policy_id.unpaid_approval_mode
        return self.dvz_policy_id.approval_mode

    def _dvz_roles(self):
        self.ensure_one()
        mode = self._dvz_mode()
        if self.dvz_exception_requested and self.dvz_policy_id.exception_mode == 'all_three':
            mode = 'both'
        if mode == 'both':
            return ['hod', 'hr']
        return [mode] if mode in ('hod', 'hr') else []

    def _dvz_next_role(self):
        self.ensure_one()
        return next((r for r in self._dvz_roles() if not self[f'dvz_{r}_approved_by']), False)

    def _get_responsible_for_approval(self):
        self.ensure_one()
        if not self.dvz_policy_id:
            return super()._get_responsible_for_approval()
        policy, employee = self.dvz_policy_id.sudo(), self.employee_id.sudo()
        users = self.env['res.users']
        role = self._dvz_next_role()
        if role:
            users |= policy._approval_users(employee, role)
        if self.dvz_exception_requested and not self.dvz_management_approved_by:
            users |= policy._approval_users(employee, 'management')
        users -= employee.user_id
        if role in ('hod', 'hr'):
            users -= self.dvz_hr_approved_by if role == 'hod' else self.dvz_hod_approved_by
        return users

    def _dvz_user_allowed(self, role):
        self.ensure_one()
        if not self.dvz_policy_id:
            return False
        policy, employee = self.dvz_policy_id.sudo(), self.employee_id.sudo()
        if employee.user_id == self.env.user:
            return False
        users = policy._approval_users(employee, role)
        if self.env.user.id not in users.ids:
            return False
        if role in ('hod', 'hr'):
            other = self.dvz_hr_approved_by if role == 'hod' else self.dvz_hod_approved_by
            if other == self.env.user:
                return False
        return True

    @api.depends_context('uid')
    @api.depends('state', 'dvz_policy_id', 'dvz_hod_approved_by', 'dvz_hr_approved_by', 'dvz_management_approved_by', 'dvz_exception_requested')
    def _compute_dvz_can_approve(self):
        for leave in self:
            pending = bool(leave.dvz_policy_id and leave.state in ('confirm', 'validate1'))
            role = leave._dvz_next_role() if pending else False
            leave.dvz_can_hod_approve = pending and role == 'hod' and leave._dvz_user_allowed('hod')
            leave.dvz_can_hr_approve = pending and role == 'hr' and leave._dvz_user_allowed('hr')
            leave.dvz_can_management_approve = pending and leave.dvz_exception_requested and not leave.dvz_management_approved_by and leave._dvz_user_allowed('management')

    def _dvz_exception_valid(self, final=False):
        self.ensure_one()
        policy = self.dvz_policy_id
        if not self.dvz_exception_requested or not self.dvz_exception_reason or policy.exception_mode == 'disabled':
            return False
        if not final:
            return True  # A pending exception is reviewable, never a validated leave.
        if not self.dvz_management_approved_by:
            return False
        if policy.exception_mode == 'all_three':
            return bool(self.dvz_hod_approved_by and self.dvz_hr_approved_by)
        return True

    def _dvz_local_day(self, moment):
        self.ensure_one()
        zone = pytz.timezone(self.employee_id.sudo().tz or self.env.user.tz or 'UTC')
        return pytz.UTC.localize(fields.Datetime.to_datetime(moment)).astimezone(zone).date()

    def _dvz_assert_sources_open(self):
        """Protect the actual native dates as well as the requested local dates."""
        for leave in self:
            starts = [value for value in (leave.request_date_from,
                leave._dvz_local_day(leave.date_from) if leave.date_from else False) if value]
            ends = [value for value in (leave.request_date_to,
                leave._dvz_local_day(leave.date_to) if leave.date_to else False) if value]
            self.env['dvz.leave.settlement']._dvz_assert_period_open(
                leave.employee_id, leave.holiday_status_id,
                min(starts) if starts else False, max(ends) if ends else False)

    def _dvz_notice_count(self, submitted_day, start_day):
        """The supplied policy uses calendar-day notice."""
        self.ensure_one()
        return (start_day - submitted_day).days

    def _dvz_validate_policy(self, final=False):
        for leave in self.filtered('dvz_policy_id'):
            policy, employee = leave.dvz_policy_id.sudo(), leave.employee_id.sudo()
            if policy.company_id != employee.company_id:
                raise ValidationError(_('The employee and leave policy must belong to the same company.'))
            if leave.dvz_emergency and not policy.allow_emergency:
                raise ValidationError(_('Emergency handling is disabled in this policy.'))
            if leave.dvz_exception_requested and (policy.exception_mode == 'disabled' or not leave.dvz_exception_reason):
                raise ValidationError(_('This policy does not permit an exception, or its reason is missing.'))
            policy._validate_approvers_for_employee(employee, leave._dvz_roles() +
                (['management'] if leave.dvz_exception_requested else []))
            if leave.request_date_to and leave.request_date_from:
                if policy.date_to and leave.request_date_to > policy.date_to:
                    raise ValidationError(_('Split the request at the policy version end date.'))
                if leave.request_date_from < policy.date_from:
                    raise ValidationError(_('The leave starts before this policy version applies.'))
            exception = leave._dvz_exception_valid(final=final)
            if leave.dvz_kind == 'paid' and not exception:
                result = policy._employee_eligibility(employee, leave.request_date_from)
                if not result['eligible']:
                    raise ValidationError(_('Paid leave is not available: %s. Use the configured unpaid type or request an exception.', result['reason']))
            if leave.dvz_kind == 'wfh':
                if not policy.wfh_enabled and not exception:
                    raise ValidationError(_('Work from home is disabled by this policy.'))
                if final:
                    leave._dvz_check_wfh_task_update_for_approval()
            if exception or leave.dvz_kind == 'unpaid':
                continue
            if leave.dvz_emergency and policy.emergency_waives_notice:
                continue
            half = leave.request_date_from == leave.request_date_to and leave.request_date_from_period == leave.request_date_to_period and leave.leave_type_request_unit == 'half_day'
            required = (policy.wfh_notice_days if leave.dvz_kind == 'wfh' else
                        policy.half_day_notice_days if half else policy.full_day_notice_days)
            submitted = leave.dvz_submitted_at or leave.create_date or fields.Datetime.now()
            notice = leave._dvz_notice_count(leave._dvz_local_day(submitted), leave.request_date_from)
            if notice < required:
                raise ValidationError(_('The policy requires %s days of advance notice. Request an authorized exception if appropriate.', required))
            prior = policy.wfh_require_prior_approval if leave.dvz_kind == 'wfh' else policy.require_prior_approval
            if final and prior and leave._dvz_roles() and fields.Datetime.now() >= leave.date_from:
                raise ValidationError(_('Prior approval is required. A past absence needs an authorized exception or unpaid classification.'))
            if final and prior:
                for role in leave._dvz_roles():
                    approved_at = leave[f'dvz_{role}_approved_at']
                    if not approved_at or leave._dvz_notice_count(leave._dvz_local_day(approved_at), leave.request_date_from) < required:
                        raise ValidationError(_('Each required approver must approve at least %s notice days before the leave.', required))

    @api.model_create_multi
    def create(self, vals_list):
        clean = []
        blocked_defaults = {'default_' + name for name in _AUDIT_FIELDS}
        if any(k in self.env.context for k in blocked_defaults):
            raise AccessError(_('Approval evidence and policy references cannot be supplied as context defaults.'))
        defaults = self.default_get(['employee_id', 'holiday_status_id', 'request_date_from', 'request_date_to'])
        for original in vals_list:
            vals = dict(original)
            for key, value in defaults.items():
                vals.setdefault(key, value)
            if not self._dvz_is_internal() and set(vals) & _AUDIT_FIELDS:
                raise AccessError(_('Policy references and approval evidence are assigned by the workflow.'))
            employee = self.env['hr.employee'].browse(vals.get('employee_id'))
            start = fields.Date.to_date(vals.get('request_date_from')) or fields.Date.context_today(self)
            type_id = vals.get('holiday_status_id')
            policy = self._dvz_policy_for_request(employee, self.env['hr.leave.type'].browse(type_id), start)
            if employee and type_id:
                self.env['dvz.leave.settlement']._dvz_assert_period_open(employee, self.env['hr.leave.type'].browse(type_id), start, fields.Date.to_date(vals.get('request_date_to')) or start)
            if policy:
                if set(vals) & _NATIVE_COMPUTED_FIELDS or any('default_' + key in self.env.context for key in _NATIVE_COMPUTED_FIELDS):
                    raise AccessError(_('Provide request dates and periods; working duration is computed by Odoo.'))
                if vals.get('state', 'confirm') != 'confirm':
                    raise AccessError(_('New policy-controlled requests must start awaiting approval.'))
                vals.update(dvz_policy_id=policy.id, dvz_policy_version=policy.version, dvz_submitted_at=fields.Datetime.now(), state='confirm')
            clean.append(vals)
        # Parent create may auto-approve a no-validation type. The policy override below
        # still verifies every policy rule and required role in that call.
        managed_batch = any(vals.get('dvz_policy_id') for vals in clean)
        safe_context = {k: v for k, v in self.env.context.items() if not managed_batch or k not in _NATIVE_SKIP_FLAGS}
        leaves = super(HrLeave, self.with_context(safe_context)._dvz_internal()).create(clean)
        leaves._dvz_assert_sources_open()
        leaves._dvz_validate_policy()
        for leave in leaves.filtered(lambda l: l.dvz_policy_id and l.state == 'confirm' and not l._dvz_roles() and not l.dvz_exception_requested):
            leave.action_approve()
        return leaves.with_context(_dvz_policy_internal=None)

    def write(self, vals):
        vals = dict(vals)
        managed = self.filtered('dvz_policy_id')
        internal = self._dvz_is_internal()
        request_fields = self._dvz_request_field_names()
        if set(vals) & (request_fields | _NATIVE_COMPUTED_FIELDS | {'state'}):
            employees = set(self.employee_id.ids)
            if vals.get('employee_id'):
                employees.add(vals['employee_id'])
            if employees:
                self.env.cr.execute('SELECT id FROM hr_employee WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(sorted(employees))])
            self._dvz_assert_sources_open()
        if not internal:
            if set(vals) & _AUDIT_FIELDS:
                raise AccessError(_('Approval evidence and policy references cannot be edited directly.'))
            if managed and set(vals) & {'validation_type', 'leave_type_request_unit', 'request_unit_half', 'request_unit_hours', 'first_approver_id', 'second_approver_id', 'resource_calendar_id'}:
                raise AccessError(_('Do not modify related time-off type settings on a request.'))
            if managed and vals.get('state') in ('validate1', 'validate'):
                raise AccessError(_('Use the policy approval buttons to approve this request.'))
            if managed and set(vals) & {'date_from', 'date_to', 'number_of_days', 'number_of_hours'}:
                raise AccessError(_('Use request dates and periods; Odoo calculates the working duration.'))
            if set(vals) & request_fields:
                if any(l.state != 'confirm' for l in managed):
                    raise UserError(_('Reset approval before changing an approved or reviewed request.'))
                vals.update({f'dvz_{role}_{suffix}': False for role in ('hod', 'hr', 'management') for suffix in ('approved_by', 'approved_at')})
            if vals.get('state') == 'confirm':
                vals.update({f'dvz_{role}_{suffix}': False for role in ('hod', 'hr', 'management') for suffix in ('approved_by', 'approved_at')})
        safe_context = dict(self.env.context) if internal or not managed else {k: v for k, v in self.env.context.items() if k not in _NATIVE_SKIP_FLAGS}
        result = super(HrLeave, self.with_context(safe_context)._dvz_internal()).write(vals)
        if set(vals) & (request_fields | _NATIVE_COMPUTED_FIELDS | {'state'}):
            self._dvz_assert_sources_open()
        if not internal and set(vals) & request_fields:
            for leave in self:
                policy = self._dvz_policy_for_request(leave.employee_id, leave.holiday_status_id, leave.request_date_from)
                applies = bool(policy)
                if applies and leave.state != 'confirm':
                    raise AccessError(_('Reset the request before changing it to a policy-controlled type.'))
                super(HrLeave, leave._dvz_internal()).write({'dvz_policy_id': policy.id if applies else False, 'dvz_policy_version': policy.version if applies else 0,
                    'dvz_submitted_at': fields.Datetime.now() if applies else False})
            self._dvz_validate_policy()
        if not internal and vals.get('dvz_task_update'):
            for leave in self.filtered(lambda l: l.dvz_kind == 'wfh' and l.dvz_return_review and l._dvz_task_update_complete()):
                leave._dvz_internal().write({'dvz_return_review': False, 'dvz_violation_reason': False})
        return result

    def _get_next_states_by_state(self):
        result = super()._get_next_states_by_state()
        if not self.dvz_policy_id:
            return result
        for states in result.values():
            states.discard('validate')
            states.discard('validate1')
        if self.state in ('confirm', 'validate1'):
            roles, role = self._dvz_roles(), self._dvz_next_role()
            if (role and self._dvz_user_allowed(role)) or not roles:
                target = 'validate1' if len(roles) == 2 and not any(self[f'dvz_{r}_approved_by'] for r in roles) else 'validate'
                result[self.state].add(target)
        return result

    def _check_approval_update(self, state, raise_if_not_possible=True):
        managed = self.filtered('dvz_policy_id')
        others = self - managed
        if others and not super(HrLeave, others)._check_approval_update(state, raise_if_not_possible):
            return False
        for leave in managed:
            if state in ('validate1', 'validate'):
                valid = state in leave._get_next_states_by_state().get(leave.state, set())
                if leave._dvz_is_internal() and state == 'validate':
                    valid = all(leave[f'dvz_{r}_approved_by'] for r in leave._dvz_roles())
                if leave._dvz_is_internal() and state == 'validate1':
                    roles = leave._dvz_roles()
                    first_stage = len(roles) == 2 and bool(leave[f'dvz_{roles[0]}_approved_by']) and not leave[f'dvz_{roles[1]}_approved_by']
                    waiting_management = (leave.dvz_exception_requested and not leave.dvz_management_approved_by
                                          and all(leave[f'dvz_{role}_approved_by'] for role in roles))
                    valid = first_stage or waiting_management
                if not valid:
                    if raise_if_not_possible:
                        raise AccessError(_('The configured approval sequence has not been completed.'))
                    return False
                if not leave.has_access('write'):
                    if raise_if_not_possible:
                        raise AccessError(_('You do not have write access to this request.'))
                    return False
            elif not super(HrLeave, leave)._check_approval_update(state, raise_if_not_possible):
                return False
        return True

    def _check_double_validation_rules(self, employees, state):
        # Managed role checks enforce the HOD and HR approvals. Core rules
        # remain untouched for all requests outside this policy addon.
        unmanaged = self.filtered(lambda l: not l.dvz_policy_id)
        if unmanaged or not self:
            return super(HrLeave, unmanaged or self)._check_double_validation_rules(employees, state)
        return None

    def _dvz_approve(self, role=False):
        self.ensure_one()
        self.check_access('write')
        self._dvz_assert_sources_open()
        self.env.cr.execute('SELECT id FROM hr_leave WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset(['state', 'dvz_hod_approved_by', 'dvz_hr_approved_by', 'dvz_management_approved_by'])
        if self.state not in ('confirm', 'validate1'):
            raise UserError(_('This request is not awaiting approval.'))
        roles = self._dvz_roles()
        next_role = self._dvz_next_role()
        if next_role:
            role = role or next_role
            if role != next_role or not self._dvz_user_allowed(role):
                raise AccessError(_('Only the next configured approver can approve this request.'))
            self._dvz_internal().write({f'dvz_{role}_approved_by': self.env.uid, f'dvz_{role}_approved_at': fields.Datetime.now()})
        elif role:
            raise UserError(_('This role has already completed its required approval.'))
        final = not self._dvz_next_role()
        if final:
            if self.dvz_exception_requested and not self._dvz_exception_valid(final=True):
                if self.state != 'validate1':
                    self._dvz_internal().write({'state': 'validate1'})
                self.activity_update()
                return True
            self._dvz_validate_policy(final=True)
            # Keep native resource, meeting, notification and balance behaviour.
            super(HrLeave, self._dvz_internal())._action_validate(check_state=False)
        else:
            self._dvz_internal().write({'state': 'validate1', 'first_approver_id': self.env.user.employee_id.id})
            self.activity_update()
        return True

    def action_approve(self, check_state=True):
        unmanaged = self.filtered(lambda l: not l.dvz_policy_id)
        if unmanaged:
            super(HrLeave, unmanaged).action_approve(check_state=check_state)
        for leave in self.filtered('dvz_policy_id'):
            leave._dvz_approve()
        return True

    def action_refuse(self):
        unmanaged = self.filtered(lambda leave: not leave.dvz_policy_id)
        if unmanaged:
            super(HrLeave, unmanaged).action_refuse()
        managed = self - unmanaged
        if managed:
            # Core refusal records the current actor in native approver fields.
            # Permit that trusted operation while keeping direct API writes barred.
            managed.check_access('write')
            super(HrLeave, managed._dvz_internal()).action_refuse()
        return True

    def _action_validate(self, check_state=True):
        if self.filtered('dvz_policy_id') and not self._dvz_is_internal():
            raise AccessError(_('Complete the policy approval workflow before validation.'))
        return super()._action_validate(check_state=check_state)

    def action_dvz_hod_approve(self):
        for leave in self:
            if not leave.dvz_policy_id:
                raise UserError(_('This request does not have a leave policy.'))
            leave._dvz_approve('hod')
        return True

    def action_dvz_hr_approve(self):
        for leave in self:
            if not leave.dvz_policy_id:
                raise UserError(_('This request does not have a leave policy.'))
            leave._dvz_approve('hr')
        return True

    def action_dvz_management_approve(self):
        for leave in self:
            leave.check_access('write')
            leave._dvz_assert_sources_open()
            self.env.cr.execute('SELECT id FROM hr_leave WHERE id = %s FOR UPDATE', [leave.id])
            leave.invalidate_recordset(['state', 'dvz_management_approved_by', 'dvz_exception_requested', 'dvz_exception_reason'])
            if leave.state not in ('confirm', 'validate1') or not leave.dvz_exception_requested or not leave._dvz_user_allowed('management'):
                raise AccessError(_('Only a configured management approver can approve a pending exception.'))
            if leave.dvz_policy_id.exception_mode == 'disabled' or not leave.dvz_exception_reason:
                raise UserError(_('A permitted exception and its reason are required.'))
            if leave.dvz_management_approved_by:
                raise UserError(_('Management has already approved this exception.'))
            leave._dvz_internal().write({'dvz_management_approved_by': self.env.uid, 'dvz_management_approved_at': fields.Datetime.now()})
            if not leave._dvz_next_role():
                leave._dvz_approve()
            else:
                leave.activity_ids.filtered(lambda activity: activity.automated and activity.activity_type_id in (
                    self.env.ref('hr_holidays.mail_act_leave_approval'),
                    self.env.ref('hr_holidays.mail_act_leave_second_approval'))).unlink()
                leave.activity_update()
        return True

    def action_dvz_convert_unpaid(self):
        if not self.env.user.has_group('hr_holidays.group_hr_holidays_manager'):
            raise AccessError(_('Only a Time Off Administrator can classify an actual unpaid absence.'))
        for leave in self:
            leave.check_access('write')
            policy = leave.dvz_policy_id
            if not policy or not policy.unpaid_leave_type_id or not leave.dvz_absence_reference:
                raise UserError(_('A policy, unpaid type and verified absence evidence are required.'))
            if leave.date_to >= fields.Datetime.now():
                raise UserError(_('A prospective request is not proof of an actual unauthorized absence.'))
            if leave.dvz_kind == 'unpaid' or leave.state in ('cancel', 'refuse'):
                raise UserError(_('This request cannot be converted to unpaid absence.'))
            action = policy.wfh_unapproved_action if leave.dvz_kind == 'wfh' else policy.unauthorized_action
            if action != 'unpaid':
                raise UserError(_('This policy is configured for review only; it does not authorize unpaid conversion.'))
            source_unit, target_unit = leave.leave_type_request_unit, policy.unpaid_leave_type_id.request_unit
            partial = source_unit == 'half_day' and (
                leave.request_date_from_period == 'pm' or leave.request_date_to_period == 'am')
            if source_unit not in ('day', 'half_day') or target_unit not in ('day', 'half_day') or (partial and target_unit == 'day'):
                raise UserError(_('Select compatible full/half-day units so unpaid classification preserves the actual absence.'))
            original_exception_reason = leave.dvz_exception_reason if leave.dvz_exception_requested else False
            leave._dvz_internal().write({'state': 'confirm', 'dvz_original_type_id': leave.holiday_status_id.id,
                'holiday_status_id': policy.unpaid_leave_type_id.id,
                'dvz_exception_requested': False, 'dvz_exception_reason': False,
                **{f'dvz_{r}_{s}': False for r in ('hod', 'hr', 'management') for s in ('approved_by', 'approved_at')},
                'dvz_violation_reason': _('Actual absence recorded as unpaid: %s', leave.dvz_absence_reference)})
            leave._post_leave_cancel()
            leave.message_post(body=_('Unpaid classification requires its configured approval before payroll treatment. Evidence: %s', leave.dvz_absence_reference))
            if original_exception_reason:
                leave.message_post(body=_('The original exception request was closed during unpaid classification. Reason: %s', original_exception_reason))
            leave._dvz_validate_policy()
            if not leave._dvz_roles():
                leave._dvz_approve()
            else:
                leave.activity_update()
        return True

    @api.depends('date_to', 'request_date_from_period', 'request_date_to_period', 'request_date_from', 'request_date_to', 'resource_calendar_id')
    def _compute_dvz_expected_return(self):
        for leave in self:
            leave.dvz_expected_return = False
            if not (leave.dvz_policy_id and leave.leave_type_request_unit == 'half_day' and
                    leave.request_date_from == leave.request_date_to and leave.request_date_from_period == leave.request_date_to_period == 'am' and leave.date_to):
                continue
            employee = leave.employee_id.sudo()
            calendar = leave.resource_calendar_id or employee.resource_calendar_id
            if not calendar:
                continue
            zone = pytz.timezone(employee.tz or 'UTC')
            begin = pytz.UTC.localize(leave.date_to)
            end = zone.localize(datetime.combine(leave.request_date_to + timedelta(days=1), time.min))
            intervals = calendar.sudo()._work_intervals_batch(begin, end, resources=employee.resource_id,
                domain=[('time_type', '=', 'leave'), ('holiday_id', '!=', leave.id)], tz=zone, compute_leaves=True)
            for start_at, stop_at, _rec in intervals[employee.resource_id.id]:
                if stop_at > begin:
                    leave.dvz_expected_return = max(start_at, begin).astimezone(pytz.UTC).replace(tzinfo=None)
                    break

    def _dvz_review_activity(self, reason):
        self.ensure_one()
        self._dvz_internal().write({'dvz_return_review': True, 'dvz_violation_reason': reason})
        if not self.activity_ids.filtered(lambda a: a.summary == _('Leave policy review')):
            for user in self.dvz_policy_id.sudo()._approval_users(self.employee_id.sudo(), 'hr'):
                self.activity_schedule('mail.mail_activity_data_todo', user_id=user.id,
                                       summary=_('Leave policy review'), note=reason)

    def action_dvz_mark_failed_return(self):
        if not self.env.user.has_group('hr_holidays.group_hr_holidays_manager'):
            raise AccessError(_('Only a Time Off Administrator can confirm a failed return.'))
        for leave in self:
            leave.check_access('write')
            if not leave.dvz_policy_id or leave.dvz_policy_id.half_day_return_action == 'none':
                raise UserError(_('Half-day return correction is disabled by this policy.'))
            if not leave.dvz_return_reference or leave.date_to >= fields.Datetime.now():
                raise UserError(_('Provide verified return evidence for an actual completed absence.'))
            if (leave.dvz_kind != 'paid' or leave.request_date_from != leave.request_date_to
                    or leave.request_date_from_period != 'am' or leave.request_date_to_period != 'am'
                    or leave.leave_type_request_unit != 'half_day' or not leave.dvz_expected_return):
                raise UserError(_('Only a morning paid half-day with a scheduled return later that day can use the failed-return rule.'))
            if leave.state != 'validate':
                raise UserError(_('The failed-return rule applies to an approved morning half-day. Review an unapproved absence through its own approval or unpaid workflow.'))
            if leave.dvz_expected_return >= fields.Datetime.now():
                raise UserError(_('The designated return time has not passed.'))
            if leave.dvz_policy_id.half_day_return_action == 'review':
                leave._dvz_review_activity(_('Verified failed return requires HR review: %s', leave.dvz_return_reference))
                continue
            leave._dvz_internal().write({'request_date_from_period': 'am', 'request_date_to_period': 'pm',
                'dvz_return_review': False, 'dvz_violation_reason': _('Verified failed return converted to a full day: %s', leave.dvz_return_reference)})
            leave._compute_duration()
            leave._check_validity()
            leave._amend_resource_leave_dates()
            if leave.meeting_id:
                leave.meeting_id.write({'start': leave.date_from, 'stop': leave.date_to, 'allday': True})
            leave.message_post(body=_('Half-day corrected to a full day under the return rule. Evidence: %s', leave.dvz_return_reference))
        return True

    def unlink(self):
        self._dvz_assert_sources_open()
        return super().unlink()
