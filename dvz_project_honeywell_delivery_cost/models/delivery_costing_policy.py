import json


SCOPE_PARAMETER = 'dvz_project_honeywell_delivery_cost.scope'
ACCOUNTS_PARAMETER = 'dvz_project_honeywell_delivery_cost.analytic_account_ids'

DELIVERY_COSTING_SCOPES = [
    ('all', 'All Projects'),
    ('none', 'None'),
    ('selected', 'Selected Projects'),
]


def get_delivery_costing_policy(env):
    """Read the global policy, retaining the old checkbox's account-wide scope."""
    parameters = env['ir.config_parameter'].sudo()
    scope = parameters.get_param(SCOPE_PARAMETER, 'none')
    if scope not in {'all', 'none', 'selected'}:
        scope = 'none'
    try:
        account_ids = json.loads(parameters.get_param(ACCOUNTS_PARAMETER, '[]'))
    except (ValueError, TypeError):
        account_ids = []
    if not isinstance(account_ids, list):
        account_ids = []
    return scope, {
        account_id for account_id in account_ids
        if type(account_id) is int and account_id > 0
    }


def enabled_delivery_costing_accounts(env, scope, account_ids):
    """Find accounts for the enablement backfill, including archived accounts."""
    Account = env['account.analytic.account'].sudo().with_context(active_test=False)
    if scope == 'all':
        return Account.search([])
    if scope == 'selected':
        return Account.browse(sorted(account_ids)).exists()
    return Account.browse()
