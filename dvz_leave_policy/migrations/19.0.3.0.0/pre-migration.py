"""Protect existing balances before reducing the addon to the supplied policy."""
from odoo.exceptions import UserError


# Only internal identifiers are interpolated. All values remain SQL parameters.
_REMOVED_SETTINGS = {
    "is_default": False, "year_start_month": "1", "allocation_frequency": "annual",
    "auto_allocation": False, "proration_method": "daily", "eligibility_mode": "confirmed",
    "probation_months": 0, "probation_access": "unpaid", "minimum_service_days": 0,
    "allow_negative": False, "approval_order": "hod_hr", "distinct_approvers": True,
    "allow_self_approval": False, "hod_source": "employee", "notice_day_basis": "calendar",
    "automatic_return_check": False, "return_grace_minutes": 0, "unauthorized_threshold": 0,
    "wfh_days_per_month": 0, "year_end_action": "encash", "carry_limit": 0,
    "carry_validity_months": 0, "encashment_rate_mode": "manual",
    "unpaid_request_unit": "follow", "wfh_request_unit": "follow",
    "unpaid_public_holidays": "follow", "wfh_public_holidays": "follow",
    "unpaid_approval_order": "follow", "wfh_approval_order": "follow",
    "management_approval_timing": "any", "allow_full_day_requests": True,
    "allow_morning_half_day": True, "allow_afternoon_half_day": True,
    "min_paid_request_days": 0, "max_paid_request_days": 0, "max_paid_requests_month": 0,
    "max_advance_days": 0, "allow_backdated_requests": True, "max_backdate_days": 0,
    "allow_cross_policy_year": True, "request_reason_required": False,
    "request_evidence_mode": "never", "max_concurrent_department_paid": 0,
    "emergency_reason_required": False, "wfh_eligibility_mode": "paid_eligible",
    "wfh_update_delivery_mode": "sent", "wfh_update_recipient_mode": "both",
    "wfh_update_timing": "after_start", "wfh_update_deadline_mode": "leave_end",
    "wfh_update_grace_hours": 0, "return_expectation": "same_day",
    "encashment_max_days": 0, "encashment_min_days": 0, "encashment_rounding_step": 0,
    "hour_settlement_mode": "block",
}


def _columns(cr, table):
    cr.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s", [table])
    return {row[0] for row in cr.fetchall()}


def migrate(cr, version):
    columns = _columns(cr, "dvz_leave_policy")
    if not columns:
        return
    used = ["p.state IN ('active', 'retired')"]
    for table, link in (
        ("hr_leave", "dvz_policy_id"), ("hr_leave_allocation", "dvz_policy_id"),
        ("dvz_leave_settlement", "policy_id"),
    ):
        if link in _columns(cr, table):
            used.append("EXISTS (SELECT 1 FROM %s u WHERE u.%s = p.id)" % (table, link))
    conditions, parameters = [], []
    for name, supported in _REMOVED_SETTINGS.items():
        if name in columns:
            conditions.append("(p.%s IS NOT NULL AND p.%s IS DISTINCT FROM %%s)" % (name, name))
            parameters.append(supported)
    if conditions:
        cr.execute(
            "SELECT p.id, p.name FROM dvz_leave_policy p WHERE (%s) AND (%s) ORDER BY p.id LIMIT 10"
            % (" OR ".join(used), " OR ".join(conditions)), parameters)
        incompatible = cr.fetchall()
        if incompatible:
            raise UserError(
                "This policy-only version cannot silently remove advanced settings from active or used policies. "
                "Keep the current version until those settings and historical balances have a reviewed migration "
                "or a separate extension. Affected policies: %s" % ", ".join("%s (%s)" % (name, ident)
                    for ident, name in incompatible))

    allocation_columns = _columns(cr, "hr_leave_allocation")
    if "dvz_allocation_kind" in allocation_columns:
        cr.execute(
            "SELECT id FROM hr_leave_allocation WHERE dvz_policy_id IS NOT NULL "
            "AND dvz_allocation_kind IS NOT NULL AND dvz_allocation_kind <> 'annual' LIMIT 1")
        if cr.fetchone():
            raise UserError(
                "Existing monthly or carry-forward allocations need a reviewed migration before "
                "installing this annual-policy-only version.")

    settlement_columns = _columns(cr, "dvz_leave_settlement")
    checks = []
    for field in ("carry_days", "expired_days", "source_unused_hours", "hours_per_day_snapshot",
                  "carry_hours", "encash_hours", "expired_hours"):
        if field in settlement_columns:
            checks.append("ABS(COALESCE(%s, 0)) > 0.000001" % field)
    if "carry_allocation_id" in settlement_columns:
        checks.append("carry_allocation_id IS NOT NULL")
    if "source_unit" in settlement_columns:
        checks.append("source_unit = 'hour'")
    if {"encash_days", "unused_days"}.issubset(settlement_columns):
        checks.append("ABS(COALESCE(encash_days, 0) - COALESCE(unused_days, 0)) > 0.000001")
    if checks:
        cr.execute(
            "SELECT id FROM dvz_leave_settlement WHERE %s ORDER BY id LIMIT 10" % " OR ".join(checks))
        incompatible = cr.fetchall()
        if incompatible:
            raise UserError(
                "Existing carry, expiry, hourly or limited-payout settlements must retain their historical "
                "calculation. Review their migration before installing the policy-only version. "
                "Settlement IDs: %s" % ", ".join(str(row[0]) for row in incompatible))

    # Stop obsolete jobs before the new registry loads. The post-migration removes
    # only these two addon-owned jobs; no employee or policy balance is changed.
    cr.execute(
        "UPDATE ir_cron SET active = FALSE WHERE id IN ("
        "SELECT res_id FROM ir_model_data WHERE module = %s AND model = 'ir.cron' "
        "AND name IN %s)",
        ["dvz_leave_policy", ("cron_dvz_policy_allocations", "cron_dvz_policy_return_review")])

