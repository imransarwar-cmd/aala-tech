"""Database integration tests; run on an Odoo 19 staging database, not production."""
from collections import defaultdict

from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from ..models.internal_transfer import AccountInternalTransfer


@tagged('post_install', '-at_install')
class TestInternalTransferBridge(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Transfer = cls.env['account.internal.transfer']
        cls.source_account = cls._new_account('DVZIT101', 'DVZ Source', 'asset_cash')
        cls.destination_account = cls._new_account('DVZIT102', 'DVZ Destination', 'asset_cash')
        cls.bridge = cls._new_account('DVZIT103', 'Internal Transfer Bridge Account', 'asset_current', True)
        cls.company.transfer_account_id = cls.bridge
        cls.source_journal = cls.env['account.journal'].create({
            'name': 'DVZ Test Source', 'code': 'DVZS', 'type': 'bank',
            'company_id': cls.company.id, 'default_account_id': cls.source_account.id,
        })
        cls.destination_journal = cls.env['account.journal'].create({
            'name': 'DVZ Test Destination', 'code': 'DVZD', 'type': 'cash',
            'company_id': cls.company.id, 'default_account_id': cls.destination_account.id,
        })
        cls.entry_journal = cls.company_data['default_journal_misc']

    @classmethod
    def _new_account(cls, code, name, account_type, reconcile=False):
        return cls.env['account.account'].create({
            'name': name, 'code': code, 'account_type': account_type,
            'reconcile': reconcile, 'company_ids': [(6, 0, cls.company.ids)],
        })

    def _transfer(self, **overrides):
        values = {
            'company_id': self.company.id,
            'date': fields.Date.context_today(self.Transfer),
            'source_journal_id': self.source_journal.id,
            'destination_journal_id': self.destination_journal.id,
            'entry_journal_id': self.entry_journal.id,
            'amount': 1000.0,
        }
        values.update(overrides)
        return self.Transfer.create(values)

    def test_defaults_to_company_bridge(self):
        transfer = self._transfer()
        self.assertEqual(transfer.bridge_account_id, self.bridge)
        defaults = self.Transfer.with_context(default_company_id=self.company.id).default_get(
            ['company_id', 'bridge_account_id']
        )
        self.assertEqual(defaults['bridge_account_id'], self.bridge.id)

    def test_four_line_post_and_bridge_reconciliation(self):
        transfer = self._transfer()
        transfer.action_post()
        self.assertEqual(transfer.state, 'posted')
        self.assertEqual(transfer.move_id.state, 'posted')
        self.assertEqual(transfer.move_id.journal_id, self.entry_journal)
        lines = transfer.move_id.line_ids
        self.assertEqual(len(lines), 4)
        self.assertAlmostEqual(sum(lines.mapped('balance')), 0.0)
        self.assertAlmostEqual(sum(lines.filtered(lambda l: l.account_id == self.source_account).mapped('balance')), -1000.0)
        self.assertAlmostEqual(sum(lines.filtered(lambda l: l.account_id == self.destination_account).mapped('balance')), 1000.0)
        bridge_lines = lines.filtered(lambda l: l.account_id == self.bridge)
        self.assertEqual(len(bridge_lines), 2)
        self.assertTrue(all(bridge_lines.mapped('reconciled')))
        self.assertAlmostEqual(sum(bridge_lines.mapped('balance')), 0.0)
        self.assertFalse(lines.tax_ids)

    def test_missing_bridge_blocks_posting(self):
        transfer = self._transfer(bridge_account_id=False)
        with self.assertRaisesRegex(UserError, 'Bridge Account'):
            transfer.action_post()
        self.assertEqual(transfer.state, 'draft')
        self.assertFalse(transfer.move_id)

    def test_non_reconcilable_bridge_rejected(self):
        account = self._new_account('DVZIT104', 'Non-reconcilable bridge', 'asset_current')
        with self.assertRaises(UserError), self.cr.savepoint():
            self._transfer(bridge_account_id=account.id)

    def test_bridge_cannot_be_a_liquidity_account(self):
        with self.assertRaises(UserError), self.cr.savepoint():
            self._transfer(bridge_account_id=self.source_account.id)

    def test_same_source_destination_rejected(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._transfer(destination_journal_id=self.source_journal.id)

    def test_zero_and_negative_amounts_rejected(self):
        for amount in (0.0, -1.0):
            with self.subTest(amount=amount), self.assertRaises(ValidationError), self.cr.savepoint():
                self._transfer(amount=amount)

    def test_duplicate_post_is_blocked(self):
        transfer = self._transfer()
        transfer.action_post()
        move = transfer.move_id
        with self.assertRaises(UserError):
            transfer.action_post()
        self.assertEqual(transfer.move_id, move)

    def test_posted_bridge_and_state_cannot_be_written(self):
        transfer = self._transfer()
        transfer.action_post()
        for values in ({'bridge_account_id': False}, {'amount': 2000}, {'state': 'draft'}):
            with self.subTest(values=values), self.assertRaises(UserError):
                transfer.write(values)

    def test_reversal_restores_all_ledger_balances(self):
        transfer = self._transfer()
        transfer.action_post()
        transfer.action_reverse()
        self.assertEqual(transfer.state, 'reversed')
        self.assertEqual(transfer.reversal_move_id.reversed_entry_id, transfer.move_id)
        self.assertEqual(len(transfer.reversal_move_id.line_ids), 4)
        balances = defaultdict(float)
        for line in (transfer.move_id + transfer.reversal_move_id).line_ids:
            balances[line.account_id.id] += line.balance
        for balance in balances.values():
            self.assertAlmostEqual(balance, 0.0)
        with self.assertRaises(UserError):
            transfer.action_reverse()

    def test_reversal_uses_original_accounts_not_new_journal_defaults(self):
        transfer = self._transfer()
        transfer.action_post()
        original_accounts = transfer.move_id.line_ids.account_id
        replacement = self._new_account('DVZIT105', 'Replacement source', 'asset_cash')
        self.source_journal.default_account_id = replacement
        transfer.action_reverse()
        self.assertEqual(transfer.reversal_move_id.line_ids.account_id, original_accounts)
        self.assertNotIn(replacement, transfer.reversal_move_id.line_ids.account_id)

    def test_legacy_two_line_transfer_can_be_reversed_without_bridge(self):
        transfer = self._transfer(bridge_account_id=False)
        original = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.entry_journal.id,
            'date': transfer.date, 'company_id': self.company.id,
            'line_ids': [
                (0, 0, {'account_id': self.destination_account.id, 'debit': 1000.0, 'credit': 0.0}),
                (0, 0, {'account_id': self.source_account.id, 'debit': 0.0, 'credit': 1000.0}),
            ],
        })
        original.action_post()
        # Simulate an already-existing v19.0.1.1.0 database record.
        super(AccountInternalTransfer, transfer).write({'move_id': original.id, 'state': 'posted'})
        transfer.action_reverse()
        self.assertFalse(transfer.bridge_account_id)
        self.assertEqual(len(original.line_ids), 2)
        self.assertEqual(len(transfer.reversal_move_id.line_ids), 2)
        self.assertEqual(transfer.reversal_move_id.reversed_entry_id, original)

    def test_copy_of_posted_transfer_is_a_new_draft(self):
        transfer = self._transfer()
        transfer.action_post()
        duplicate = transfer.copy()
        self.assertEqual(duplicate.state, 'draft')
        self.assertFalse(duplicate.move_id)
        self.assertFalse(duplicate.reversal_move_id)
        self.assertNotEqual(duplicate.name, transfer.name)
        self.assertEqual(duplicate.bridge_account_id, self.bridge)
