"""Move the preserved per-analytic selections into global configuration."""

import json

from odoo import api
from odoo.api import SUPERUSER_ID


SNAPSHOT_KEY = (
    'dvz_project_honeywell_delivery_cost.legacy_enabled_analytic_ids_19_0_1_8_0'
)
SCOPE_KEY = 'dvz_project_honeywell_delivery_cost.scope'
ACCOUNTS_KEY = 'dvz_project_honeywell_delivery_cost.analytic_account_ids'


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    parameters = env['ir.config_parameter']
    snapshot = parameters.search(
        [('key', '=', SNAPSHOT_KEY)], limit=1
    )
    if not snapshot:
        return

    legacy_ids = json.loads(snapshot.value)
    if not isinstance(legacy_ids, list) or any(
        type(account_id) is not int or account_id <= 0
        for account_id in legacy_ids
    ):
        raise ValueError('Invalid Honeywell delivery costing migration snapshot.')

    Account = env['account.analytic.account']
    accounts = (
        Account
        .with_context(active_test=False)
        .browse(legacy_ids)
        .exists()
    )
    parameters.set_param(ACCOUNTS_KEY, json.dumps(sorted(set(accounts.ids))))
    parameters.set_param(SCOPE_KEY, 'selected' if accounts else 'none')
    Account.invalidate_model(['dvz_honeywell_delivery_costing'])

    # Only remove the recovery snapshot after both settings have been saved.
    # Existing cost lines are deliberately neither synchronized nor deleted.
    snapshot.unlink()
