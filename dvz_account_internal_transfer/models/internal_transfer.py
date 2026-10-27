import math

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountInternalTransfer(models.Model):
    _name = 'account.internal.transfer'
    _description = 'Internal Bank/Cash Transfer'
    _order = 'date desc, id desc'
    _check_company_auto = True
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(default='New', readonly=True, copy=False, tracking=True)
    date = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True,
    )
    amount = fields.Monetary(required=True, currency_field='currency_id')
    source_journal_id = fields.Many2one(
        'account.journal', required=True, check_company=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    destination_journal_id = fields.Many2one(
        'account.journal', required=True, check_company=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    entry_journal_id = fields.Many2one(
        'account.journal', string='Transfer Entry Journal', required=True,
        check_company=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        help='Miscellaneous journal used for the four-line transfer entry.',
    )
    # Intentionally nullable, and without a field-level default: upgrading must
    # not label historical two-line transfers as having used a bridge account.
    bridge_account_id = fields.Many2one(
        'account.account', string='Internal Transfer Bridge Account',
        check_company=True, ondelete='restrict', tracking=True,
        domain="[('company_ids', 'in', [company_id]), ('active', '=', True), "
               "('account_type', '=', 'asset_current'), ('reconcile', '=', True)]",
        help='Reconcilable Current Assets account used between the source and '
             'destination accounts. New transfers default to the company\'s '
             'Inter-Banks Transfer Account, when configured. Both legs post '
             'together, so this transfer contributes zero net bridge balance.',
    )
    memo = fields.Char()
    state = fields.Selection(
        [('draft', 'Draft'), ('posted', 'Posted'), ('reversed', 'Reversed')],
        default='draft', required=True, readonly=True, copy=False, tracking=True,
    )
    move_id = fields.Many2one(
        'account.move', readonly=True, copy=False, check_company=True,
        ondelete='restrict',
    )
    reversal_move_id = fields.Many2one(
        'account.move', readonly=True, copy=False, check_company=True,
        ondelete='restrict',
    )

    @api.model
    def _company_bridge_account(self, company):
        """Reuse only an eligible configured account; never create a ledger account.

        A relational dropdown domain does not validate an assigned default.
        Keep the company default subject to the same eligibility rules so an
        unsuitable account cannot be preselected outside the filtered list.
        """
        return company.transfer_account_id.filtered(
            lambda account: account.active
            and account.account_type == 'asset_current'
            and account.reconcile
            and company in account.company_ids
        )

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        if 'bridge_account_id' in field_names and 'bridge_account_id' not in values:
            company_id = (
                values.get('company_id')
                or self.env.context.get('default_company_id')
                or self.env.company.id
            )
            company = self.env['res.company'].browse(company_id)
            values['bridge_account_id'] = self._company_bridge_account(company).id
        return values

    @api.onchange('company_id')
    def _onchange_company_id(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            rec.bridge_account_id = rec._company_bridge_account(rec.company_id)
            for field_name in (
                'source_journal_id', 'destination_journal_id', 'entry_journal_id',
            ):
                journal = rec[field_name]
                if journal and journal.company_id != rec.company_id:
                    rec[field_name] = False

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            if vals.get('state', 'draft') != 'draft' or vals.get('move_id') or vals.get('reversal_move_id'):
                raise UserError(_('Create a draft transfer and use Post Transfer to post it.'))
            company_id = (
                vals.get('company_id')
                or self.env.context.get('default_company_id')
                or self.env.company.id
            )
            company = self.env['res.company'].browse(company_id)
            if not vals.get('name') or vals['name'] == 'New':
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code(
                    'dvz.account.internal.transfer'
                ) or 'New'
            if 'bridge_account_id' not in vals:
                vals['bridge_account_id'] = self._company_bridge_account(company).id
        return super().create(vals_list)

    @api.constrains(
        'amount', 'source_journal_id', 'destination_journal_id',
        'entry_journal_id', 'company_id', 'bridge_account_id',
    )
    def _validate_transfer(self):
        for rec in self:
            currency = rec.company_id.currency_id
            if not math.isfinite(rec.amount) or currency.round(rec.amount) <= 0:
                raise ValidationError(_('The transfer amount must be greater than zero after currency rounding.'))
            if rec.source_journal_id and rec.source_journal_id == rec.destination_journal_id:
                raise ValidationError(_('Source and destination journals must differ.'))
            for journal in (rec.source_journal_id, rec.destination_journal_id, rec.entry_journal_id):
                if journal and journal.company_id != rec.company_id:
                    raise ValidationError(_('All journals must belong to the selected company.'))
            for journal in (rec.source_journal_id, rec.destination_journal_id):
                if journal and journal.type not in ('bank', 'cash'):
                    raise ValidationError(_('Source and destination must be bank or cash journals.'))
            if rec.entry_journal_id and rec.entry_journal_id.type != 'general':
                raise ValidationError(_('The Transfer Entry Journal must be a miscellaneous journal.'))
            # Empty is allowed on legacy records and API-created drafts, but is
            # rejected by _bridge_account() when a new transfer is posted.
            if rec.bridge_account_id:
                rec._bridge_account()

    def _check_account_usable(self, account):
        self.ensure_one()
        if 'active' in account._fields and not account.active:
            raise UserError(_('Selected accounts must not be archived.'))
        if 'deprecated' in account._fields and account.deprecated:
            raise UserError(_('Selected accounts must not be deprecated.'))
        if 'company_ids' in account._fields and self.company_id not in account.company_ids:
            raise UserError(_('All accounts must be available to the selected company.'))
        if account.currency_id and account.currency_id != self.company_id.currency_id:
            raise UserError(_('This module supports company-currency transfers only. A selected account uses a different currency.'))

    def _accounts(self):
        """Keep the existing source and destination default-account selection."""
        self.ensure_one()
        source = self.source_journal_id.default_account_id
        destination = self.destination_journal_id.default_account_id
        if not source or not destination:
            raise UserError(_('Configure a Default Account on both the source and destination bank/cash journals.'))
        if source == destination:
            raise UserError(_('Source and destination journals cannot use the same ledger account.'))
        for account in (source, destination):
            self._check_account_usable(account)
        return source, destination

    def _bridge_account(self):
        self.ensure_one()
        bridge = self.bridge_account_id
        if not bridge:
            raise UserError(_('Select an Internal Transfer Bridge Account before posting.'))
        self._check_account_usable(bridge)
        if bridge.account_type != 'asset_current' or not bridge.reconcile:
            raise UserError(_('The Internal Transfer Bridge Account must be a Current Assets account with Allow Reconciliation enabled.'))
        if bridge in (
            self.source_journal_id.default_account_id,
            self.destination_journal_id.default_account_id,
        ):
            raise UserError(_('The bridge account must differ from both the source and destination accounts.'))
        return bridge

    def _prepare_move_vals(self):
        """One existing-style entry, now explicitly containing both bridge legs."""
        self.ensure_one()
        source, destination = self._accounts()
        bridge = self._bridge_account()
        currency = self.company_id.currency_id
        amount = currency.round(self.amount)
        label = _('Internal transfer: %s', self.name)
        if self.memo:
            label += ' - ' + self.memo
        outgoing_label = label + ' / ' + _('Source to bridge')
        incoming_label = label + ' / ' + _('Bridge to destination')
        legs = [
            (bridge, amount, 0.0, outgoing_label),
            (source, 0.0, amount, outgoing_label),
            (destination, amount, 0.0, incoming_label),
            (bridge, 0.0, amount, incoming_label),
        ]
        return {
            'move_type': 'entry',
            'date': self.date,
            'journal_id': self.entry_journal_id.id,
            'company_id': self.company_id.id,
            'ref': label,
            'line_ids': [
                (0, 0, {
                    'sequence': sequence * 10,
                    'name': line_label,
                    'account_id': account.id,
                    'debit': debit,
                    'credit': credit,
                    'currency_id': currency.id,
                    'amount_currency': debit - credit,
                    'tax_ids': [(5, 0, 0)],
                })
                for sequence, (account, debit, credit, line_label) in enumerate(legs, start=1)
            ],
        }

    def _reconcile_bridge(self, move):
        """Match only this entry's bridge lines, never bank statement lines."""
        self.ensure_one()
        if not self.bridge_account_id or not self.bridge_account_id.reconcile:
            return
        lines = move.line_ids.filtered(
            lambda line: line.account_id == self.bridge_account_id and not line.reconciled
        )
        if len(lines) >= 2 and self.company_id.currency_id.is_zero(sum(lines.mapped('balance'))):
            lines.reconcile()

    def _lock_for_posting_action(self):
        """Check access and serialize posting/reversal for the same transfer."""
        self.check_access('write')
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only an Accounting Manager may post or reverse a transfer.'))
        if self:
            self.flush_recordset()
            self.env.cr.execute(
                'SELECT id FROM account_internal_transfer WHERE id IN %s ORDER BY id FOR UPDATE',
                [tuple(self.ids)],
            )
            self.invalidate_recordset()

    def action_post(self):
        self._lock_for_posting_action()
        with self.env.cr.savepoint():
            for rec in self:
                if rec.state != 'draft' or rec.move_id or rec.reversal_move_id:
                    raise UserError(_('Only an unposted draft transfer can be posted.'))
                rec._validate_transfer()
                for journal in (rec.source_journal_id, rec.destination_journal_id, rec.entry_journal_id):
                    if not journal or not journal.active:
                        raise UserError(_('Select active source, destination and transfer entry journals.'))
                    if journal.currency_id and journal.currency_id != rec.company_id.currency_id:
                        raise UserError(_('This module supports company-currency transfers only. A selected journal uses a different currency.'))
                move = self.env['account.move'].with_company(rec.company_id).create(rec._prepare_move_vals())
                move.action_post()
                rec._reconcile_bridge(move)
                # Bypass only this model's public-write protection, not ORM ACLs.
                super(AccountInternalTransfer, rec).write({'move_id': move.id, 'state': 'posted'})
        return True

    def action_reverse(self):
        self._lock_for_posting_action()
        with self.env.cr.savepoint():
            for rec in self:
                if rec.state != 'posted' or not rec.move_id or rec.reversal_move_id:
                    raise UserError(_('Only a posted transfer without an existing reversal can be reversed.'))
                if rec.move_id.state != 'posted':
                    raise UserError(_('The original journal entry must still be posted.'))
                if rec.move_id.reversal_move_ids.filtered(lambda move: move.state != 'cancel'):
                    raise UserError(_('The journal entry already has a reversal. Review that reversal before continuing.'))
                # Reverse the actual saved lines. This also supports historical
                # two-line transfers and later changes to journal defaults.
                reversal = rec.move_id.with_company(rec.company_id)._reverse_moves(
                    default_values_list=[{
                        'date': fields.Date.context_today(rec),
                        'ref': _('Reversal: %s', rec.move_id.ref or rec.name),
                        'auto_post': 'no',
                    }],
                    cancel=False,
                )
                reversal.action_post()
                rec._reconcile_bridge(reversal)
                super(AccountInternalTransfer, rec).write({
                    'reversal_move_id': reversal.id, 'state': 'reversed',
                })
        return True

    def action_view_entry(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('This transfer has no journal entry yet.'))
        return {
            'type': 'ir.actions.act_window', 'name': _('Journal Entry'),
            'res_model': 'account.move', 'view_mode': 'form',
            'res_id': self.move_id.id, 'target': 'current',
        }

    def action_view_reversal(self):
        self.ensure_one()
        if not self.reversal_move_id:
            raise UserError(_('This transfer has no reversal entry.'))
        return {
            'type': 'ir.actions.act_window', 'name': _('Reversal Entry'),
            'res_model': 'account.move', 'view_mode': 'form',
            'res_id': self.reversal_move_id.id, 'target': 'current',
        }

    def write(self, vals):
        if {'state', 'move_id', 'reversal_move_id'}.intersection(vals):
            raise UserError(_('Use Post Transfer or Reverse Transfer to change the posting status.'))
        protected = {
            'name', 'date', 'company_id', 'amount', 'source_journal_id',
            'destination_journal_id', 'entry_journal_id', 'bridge_account_id', 'memo',
        }
        if protected.intersection(vals) and any(rec.state != 'draft' for rec in self):
            raise UserError(_('Posted or reversed transfers cannot be modified.'))
        if 'company_id' in vals and 'bridge_account_id' not in vals:
            company = self.env['res.company'].browse(vals['company_id'])
            vals = dict(vals, bridge_account_id=self._company_bridge_account(company).id)
        return super().write(vals)

    def unlink(self):
        if any(rec.state != 'draft' or rec.move_id or rec.reversal_move_id for rec in self):
            raise UserError(_('Only draft transfers without journal entries can be deleted.'))
        return super().unlink()
