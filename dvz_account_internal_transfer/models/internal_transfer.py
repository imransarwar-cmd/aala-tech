from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountInternalTransfer(models.Model):
    _name = 'account.internal.transfer'
    _description = 'Internal Bank/Cash Transfer'
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(default='New', readonly=True, copy=False)
    date = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=False)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    source_journal_id = fields.Many2one('account.journal', required=True, check_company=True, domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]")
    destination_journal_id = fields.Many2one('account.journal', required=True, check_company=True, domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]")
    entry_journal_id = fields.Many2one('account.journal', string='Transfer Entry Journal', required=True, check_company=True, domain="[('type', '=', 'general'), ('company_id', '=', company_id)]", help='Miscellaneous journal used to record the balanced transfer entry.')
    memo = fields.Char()
    state = fields.Selection([('draft', 'Draft'), ('posted', 'Posted'), ('reversed', 'Reversed')], default='draft', required=True, readonly=True)
    move_id = fields.Many2one('account.move', readonly=True, copy=False, check_company=True)
    reversal_move_id = fields.Many2one('account.move', readonly=True, copy=False, check_company=True)

    @api.constrains('amount', 'source_journal_id', 'destination_journal_id', 'entry_journal_id', 'company_id')
    def _validate_transfer(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_('The transfer amount must be greater than zero.'))
            if rec.source_journal_id and rec.source_journal_id == rec.destination_journal_id:
                raise ValidationError(_('Source and destination journals must differ.'))
            for journal in (rec.source_journal_id, rec.destination_journal_id, rec.entry_journal_id):
                if journal and journal.company_id != rec.company_id:
                    raise ValidationError(_('All journals must belong to the selected company.'))

    def _accounts(self):
        self.ensure_one()
        source = self.source_journal_id.default_account_id
        destination = self.destination_journal_id.default_account_id
        if not source or not destination:
            raise UserError(_('Configure a Default Account on both the source and destination bank/cash journals.'))
        if source == destination:
            raise UserError(_('Source and destination journals cannot use the same ledger account.'))
        for account in (source, destination):
            if account.deprecated:
                raise UserError(_('The journal default account must not be deprecated.'))
            if account.company_ids and self.company_id not in account.company_ids:
                raise UserError(_('The journal account is not available to the selected company.'))
        return source, destination

    def _prepare_move_vals(self, reverse=False):
        self.ensure_one()
        source, destination = self._accounts()
        debit_account, credit_account = (source, destination) if reverse else (destination, source)
        label = ('Reversal: ' if reverse else 'Internal transfer: ') + (self.memo or self.name)
        return {
            'date': fields.Date.context_today(self) if reverse else self.date,
            'journal_id': self.entry_journal_id.id,
            'company_id': self.company_id.id,
            'ref': label,
            'line_ids': [
                (0, 0, {'name': label, 'account_id': debit_account.id, 'debit': self.amount, 'credit': 0}),
                (0, 0, {'name': label, 'account_id': credit_account.id, 'debit': 0, 'credit': self.amount}),
            ],
        }

    def action_post(self):
        for rec in self:
            if rec.state != 'draft' or rec.move_id:
                raise UserError(_('Only an unposted draft transfer can be posted.'))
            rec._validate_transfer()
            rec._accounts()
            move = self.env['account.move'].with_company(rec.company_id).create(rec._prepare_move_vals())
            move.action_post()
            rec.write({'move_id': move.id, 'state': 'posted', 'name': 'TRF/%05d' % rec.id})
        return True

    def action_reverse(self):
        for rec in self:
            if rec.state != 'posted' or not rec.move_id or rec.reversal_move_id:
                raise UserError(_('Only a posted transfer without an existing reversal can be reversed.'))
            if rec.move_id.state != 'posted':
                raise UserError(_('The original journal entry must still be posted.'))
            move = self.env['account.move'].with_company(rec.company_id).create(rec._prepare_move_vals(reverse=True))
            move.action_post()
            rec.write({'reversal_move_id': move.id, 'state': 'reversed'})
        return True

    def action_view_entry(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Journal Entry'), 'res_model': 'account.move', 'view_mode': 'form', 'res_id': self.move_id.id, 'target': 'current'}

    def action_view_reversal(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Reversal Entry'), 'res_model': 'account.move', 'view_mode': 'form', 'res_id': self.reversal_move_id.id, 'target': 'current'}

    def write(self, vals):
        protected = {'date', 'company_id', 'amount', 'source_journal_id', 'destination_journal_id', 'entry_journal_id', 'memo'}
        if protected.intersection(vals) and any(rec.state != 'draft' for rec in self):
            raise UserError(_('Posted or reversed transfers cannot be modified.'))
        return super().write(vals)

    def unlink(self):
        if any(rec.state != 'draft' or rec.move_id for rec in self):
            raise UserError(_('Only draft transfers without journal entries can be deleted.'))
        return super().unlink()
