import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .delivery_costing_policy import (
    ACCOUNTS_PARAMETER,
    DELIVERY_COSTING_SCOPES,
    SCOPE_PARAMETER,
    enabled_delivery_costing_accounts,
    get_delivery_costing_policy,
)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # The Many2many is persisted as JSON in ir.config_parameter by set_values;
    # it must not be lost when Odoo cleans up transient settings records.
    dvz_honeywell_delivery_costing_scope = fields.Selection(
        selection=DELIVERY_COSTING_SCOPES,
        string='Delivery Costing Applies To',
        default='none',
        required=True,
        help='Apply delivery costing to all projects, no projects, or selected analytic accounts.',
    )
    dvz_honeywell_delivery_costing_account_ids = fields.Many2many(
        'account.analytic.account',
        'dvz_delivery_cost_settings_analytic_rel',
        'settings_id',
        'analytic_account_id',
        string='Selected Analytic Accounts',
        context={'active_test': False},
        help='Choose multiple project analytic accounts by name.',
    )

    @api.model
    def get_values(self):
        values = super().get_values()
        scope, account_ids = get_delivery_costing_policy(self.env)
        accounts = self.env['account.analytic.account'].sudo().browse(sorted(account_ids)).exists()
        values.update({
            'dvz_honeywell_delivery_costing_scope': scope,
            'dvz_honeywell_delivery_costing_account_ids': [
                fields.Command.set(accounts.ids),
            ],
        })
        return values

    def set_values(self):
        self.ensure_one()
        if not self.env.is_admin():
            raise AccessError(_('Only administrators can configure delivery costing.'))

        scope = self.dvz_honeywell_delivery_costing_scope
        account_ids = set(self.dvz_honeywell_delivery_costing_account_ids.ids)
        if scope == 'selected' and not account_ids:
            raise ValidationError(_(
                'Select at least one analytic account for Selected Projects, '
                'or choose None.'
            ))

        old_scope, old_account_ids = get_delivery_costing_policy(self.env)
        result = super().set_values()
        if (old_scope, old_account_ids) == (scope, account_ids):
            return result

        previously_enabled = enabled_delivery_costing_accounts(
            self.env, old_scope, old_account_ids,
        )
        parameters = self.env['ir.config_parameter'].sudo()
        parameters.set_param(SCOPE_PARAMETER, scope)
        parameters.set_param(ACCOUNTS_PARAMETER, json.dumps(sorted(account_ids)))
        self.env['account.analytic.account'].invalidate_model([
            'dvz_honeywell_delivery_costing',
        ])
        newly_enabled = enabled_delivery_costing_accounts(
            self.env, scope, account_ids,
        ) - previously_enabled
        # This retains the previous checkbox behavior: newly enabled accounts
        # immediately pick up their already-completed customer deliveries.
        newly_enabled._dvz_sync_all_delivery_costs()
        return result
