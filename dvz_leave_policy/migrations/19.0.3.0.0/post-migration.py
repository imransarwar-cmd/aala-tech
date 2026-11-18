"""Remove only obsolete addon-owned setup data after a successful upgrade."""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for name in ("cron_dvz_policy_allocations", "cron_dvz_policy_return_review"):
        job = env.ref("dvz_leave_policy." + name, raise_if_not_found=False)
        if job:
            job.unlink()
    legacy = env.ref("dvz_leave_policy.policy_standard_draft", raise_if_not_found=False)
    assigned = legacy and env["hr.employee"].with_context(active_test=False).search_count([
        ("dvz_leave_policy_id", "=", legacy.id)], limit=1)
    if legacy and legacy.state == "draft" and not legacy._has_usage() and not assigned:
        legacy.active = False

