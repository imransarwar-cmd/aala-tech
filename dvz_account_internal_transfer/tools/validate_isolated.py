"""Isolated tests of actual addon methods with lightweight Odoo substitutes.
These tests do not exercise the ORM, PostgreSQL, real posting or reconciliation.
"""
import importlib.util
import sys
import types
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / 'models' / 'internal_transfer.py'


class UserError(Exception):
    pass


class ValidationError(Exception):
    pass


class Model:
    def ensure_one(self):
        return self

    def __iter__(self):
        yield self

    def write(self, values):
        for key, value in values.items():
            setattr(self, key, value)
        return True


class Field:
    def __call__(self, *args, **kwargs):
        return None

    @staticmethod
    def context_today(record):
        return date(2026, 10, 27)


class Fields:
    def __getattr__(self, name):
        return Field()


def translate(message, *args, **kwargs):
    return message % (kwargs or args) if args or kwargs else message


odoo = types.ModuleType('odoo')
odoo.api = types.SimpleNamespace(
    model=lambda func: func,
    model_create_multi=lambda func: func,
    constrains=lambda *names: lambda func: func,
    onchange=lambda *names: lambda func: func,
)
odoo.fields = Fields()
odoo.models = types.SimpleNamespace(Model=Model)
odoo._ = translate
exceptions = types.ModuleType('odoo.exceptions')
exceptions.UserError = UserError
exceptions.ValidationError = ValidationError
sys.modules['odoo'] = odoo
sys.modules['odoo.exceptions'] = exceptions
spec = importlib.util.spec_from_file_location('transfer_under_test', MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Transfer = module.AccountInternalTransfer


class Record:
    def __init__(self, **values):
        self.__dict__.update(values)


class Currency(Record):
    def round(self, value):
        return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def is_zero(self, value):
        return self.round(value) == 0


class Lines(list):
    def __init__(self, values, calls=None):
        super().__init__(values)
        self.calls = [] if calls is None else calls

    def filtered(self, predicate):
        return Lines([line for line in self if predicate(line)], self.calls)

    def mapped(self, name):
        return [getattr(line, name) for line in self]

    def reconcile(self):
        self.calls.append(tuple(line.account_id.id for line in self))
        for line in self:
            line.reconciled = True


@pytest.fixture
def transfer():
    currency = Currency(id=1)
    company = Record(id=1, currency_id=currency)
    def account(identifier, kind):
        return Record(id=identifier, active=True, account_type=kind, reconcile=True,
                      company_ids=[company], currency_id=False,
                      _fields={'active': object(), 'company_ids': object()})
    source = account(101, 'asset_cash')
    destination = account(102, 'asset_cash')
    bridge = account(103, 'asset_current')
    rec = Transfer()
    rec.name = 'TRF/2026/00001'
    rec.date = date(2026, 10, 27)
    rec.company_id = company
    rec.currency_id = currency
    rec.amount = 1000.0
    rec.memo = 'Test transfer'
    rec.state = 'draft'
    rec.move_id = False
    rec.reversal_move_id = False
    rec.source_journal_id = Record(id=201, type='bank', company_id=company, default_account_id=source, active=True, currency_id=False)
    rec.destination_journal_id = Record(id=202, type='cash', company_id=company, default_account_id=destination, active=True, currency_id=False)
    rec.entry_journal_id = Record(id=203, type='general', company_id=company, active=True, currency_id=False)
    rec.bridge_account_id = bridge
    return rec


@pytest.mark.parametrize('source_type,destination_type', [
    ('bank', 'bank'), ('bank', 'cash'), ('cash', 'bank'), ('cash', 'cash'),
])
def test_all_four_transfer_types_preserve_accounts(transfer, source_type, destination_type):
    transfer.source_journal_id.type = source_type
    transfer.destination_journal_id.type = destination_type
    transfer._validate_transfer()
    values = transfer._prepare_move_vals()
    lines = [command[2] for command in values['line_ids']]
    assert len(lines) == 4
    assert values['journal_id'] == 203
    assert [line['account_id'] for line in lines] == [103, 101, 102, 103]
    assert [line['debit'] for line in lines] == [1000, 0, 1000, 0]
    assert [line['credit'] for line in lines] == [0, 1000, 0, 1000]
    assert sum(line['debit'] - line['credit'] for line in lines) == 0
    assert sum(line['debit'] - line['credit'] for line in lines if line['account_id'] == 103) == 0
    assert all(line['currency_id'] == 1 for line in lines)
    assert all(line['tax_ids'] == [(5, 0, 0)] for line in lines)
    assert all(line['amount_currency'] == line['debit'] - line['credit'] for line in lines)


def test_reference_and_memo_kept(transfer):
    assert 'TRF/2026/00001' in transfer._prepare_move_vals()['ref']
    assert 'Test transfer' in transfer._prepare_move_vals()['ref']


def test_missing_bridge(transfer):
    transfer.bridge_account_id = False
    with pytest.raises(UserError, match='Bridge Account'):
        transfer._prepare_move_vals()


@pytest.mark.parametrize('field,value', [('account_type', 'expense'), ('reconcile', False), ('active', False)])
def test_invalid_bridge(transfer, field, value):
    setattr(transfer.bridge_account_id, field, value)
    with pytest.raises(UserError):
        transfer._prepare_move_vals()


def test_bridge_cannot_be_source(transfer):
    transfer.source_journal_id.default_account_id = transfer.bridge_account_id
    with pytest.raises(UserError, match='differ from both'):
        transfer._prepare_move_vals()


def test_bridge_cannot_be_destination(transfer):
    transfer.destination_journal_id.default_account_id = transfer.bridge_account_id
    with pytest.raises(UserError, match='differ from both'):
        transfer._prepare_move_vals()


def test_same_liquidity_accounts(transfer):
    transfer.destination_journal_id.default_account_id = transfer.source_journal_id.default_account_id
    with pytest.raises(UserError, match='same ledger'):
        transfer._prepare_move_vals()


def test_wrong_company_bridge(transfer):
    transfer.bridge_account_id.company_ids = [Record(id=2)]
    with pytest.raises(UserError, match='selected company'):
        transfer._prepare_move_vals()


def test_wrong_company_journal(transfer):
    transfer.source_journal_id.company_id = Record(id=2)
    with pytest.raises(ValidationError, match='selected company'):
        transfer._validate_transfer()


def test_foreign_currency_bridge(transfer):
    transfer.bridge_account_id.currency_id = Currency(id=2)
    with pytest.raises(UserError, match='company-currency'):
        transfer._prepare_move_vals()


def test_missing_liquidity_default(transfer):
    transfer.source_journal_id.default_account_id = False
    with pytest.raises(UserError, match='Default Account'):
        transfer._prepare_move_vals()


@pytest.mark.parametrize('amount', [0.0, -10.0, 0.001, float('inf'), float('nan')])
def test_non_positive_rounded_or_nonfinite_amounts(transfer, amount):
    transfer.amount = amount
    with pytest.raises(ValidationError):
        transfer._validate_transfer()


@pytest.mark.parametrize('amount,rounded', [(0.01, 0.01), (123.456, 123.46), (999999.99, 999999.99)])
def test_currency_rounding_in_all_four_lines(transfer, amount, rounded):
    transfer.amount = amount
    transfer._validate_transfer()
    lines = [command[2] for command in transfer._prepare_move_vals()['line_ids']]
    assert all(abs(line['amount_currency']) == rounded for line in lines)
    assert sum(line['amount_currency'] for line in lines) == 0


def test_same_journals(transfer):
    transfer.destination_journal_id = transfer.source_journal_id
    with pytest.raises(ValidationError):
        transfer._validate_transfer()


def test_wrong_journal_types(transfer):
    transfer.entry_journal_id.type = 'sale'
    with pytest.raises(ValidationError):
        transfer._validate_transfer()


def test_posted_bridge_edit_blocked(transfer):
    transfer.state = 'posted'
    with pytest.raises(UserError, match='cannot be modified'):
        transfer.write({'bridge_account_id': False})


def test_public_state_edit_blocked(transfer):
    with pytest.raises(UserError, match='Use Post Transfer'):
        transfer.write({'state': 'posted'})


def test_reconciliation_selects_only_this_entry_bridge_lines(transfer):
    bridge = transfer.bridge_account_id
    source = transfer.source_journal_id.default_account_id
    destination = transfer.destination_journal_id.default_account_id
    lines = Lines([
        Record(account_id=bridge, balance=1000, reconciled=False),
        Record(account_id=source, balance=-1000, reconciled=False),
        Record(account_id=destination, balance=1000, reconciled=False),
        Record(account_id=bridge, balance=-1000, reconciled=False),
    ])
    transfer._reconcile_bridge(Record(line_ids=lines))
    assert lines.calls == [(103, 103)]
    assert [line.reconciled for line in lines] == [True, False, False, True]


def test_legacy_no_bridge_skips_bridge_matching(transfer):
    transfer.bridge_account_id = False
    lines = Lines([])
    transfer._reconcile_bridge(Record(line_ids=lines))
    assert lines.calls == []


# Regression coverage for v19.0.1.2.1 bridge dropdown and company defaults.
# The domain checks evaluate only literal conditions; they do not run Odoo's UI.
class Accounts(list):
    def filtered(self, predicate):
        return Accounts(account for account in self if predicate(account))

    @property
    def id(self):
        if len(self) > 1:
            raise ValueError('Expected at most one account')
        return self[0].id if self else False


def _bridge_domain(source, company_id=1):
    import ast
    from xml.etree import ElementTree

    if source == 'model':
        tree = ast.parse(MODULE_PATH.read_text())
        model_class = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        assignment = next(
            node for node in model_class.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'bridge_account_id'
                    for target in node.targets)
        )
        expression = ast.literal_eval(next(
            item.value for item in assignment.value.keywords if item.arg == 'domain'
        ))
    else:
        tree = ElementTree.parse(MODULE_PATH.parents[1] / 'views/internal_transfer_views.xml')
        field = tree.find(".//form//field[@name='bridge_account_id']")
        expression = field.attrib['domain']

    class SubstituteCompany(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id != 'company_id':
                raise ValueError(f'Unexpected domain variable: {node.id}')
            return ast.copy_location(ast.Constant(value=company_id), node)

    return ast.literal_eval(SubstituteCompany().visit(ast.parse(expression, mode='eval')))


def _matches_bridge_domain(account, domain):
    # Only AND-combined '=' and Many2many 'in' leaves are used by this field.
    for field_name, operator, expected in domain:
        actual = account[field_name]
        if operator == '=':
            if actual != expected:
                return False
        elif operator == 'in':
            if not set(actual).intersection(expected):
                return False
        else:
            raise AssertionError(f'Unsupported operator: {operator}')
    return True


def test_model_and_form_bridge_filters_match():
    expected = [
        ('company_ids', 'in', [1]), ('active', '=', True),
        ('account_type', '=', 'asset_current'), ('reconcile', '=', True),
    ]
    assert _bridge_domain('model') == expected
    assert _bridge_domain('form') == expected


@pytest.mark.parametrize('source', ['model', 'form'])
@pytest.mark.parametrize('changes,allowed', [
    ({}, True),
    ({'account_type': 'asset_cash'}, False),
    ({'account_type': 'expense'}, False),
    ({'account_type': 'asset_receivable'}, False),
    ({'account_type': 'liability_current'}, False),
    ({'reconcile': False}, False),
    ({'active': False}, False),
    ({'company_ids': [2]}, False),
    ({'company_ids': [1, 2]}, True),
    ({'company_ids': []}, False),
])
def test_bridge_dropdown_eligibility(source, changes, allowed):
    account = {
        'account_type': 'asset_current', 'reconcile': True,
        'active': True, 'company_ids': [1],
    }
    account.update(changes)
    assert _matches_bridge_domain(account, _bridge_domain(source)) is allowed


def test_bridge_filter_uses_selected_company():
    account = {
        'account_type': 'asset_current', 'reconcile': True,
        'active': True, 'company_ids': [2],
    }
    for source in ('model', 'form'):
        assert not _matches_bridge_domain(account, _bridge_domain(source, company_id=1))
        assert _matches_bridge_domain(account, _bridge_domain(source, company_id=2))


def test_bridge_dropdown_does_not_create_accounts_inline():
    import ast
    from xml.etree import ElementTree
    tree = ElementTree.parse(MODULE_PATH.parents[1] / 'views/internal_transfer_views.xml')
    field = tree.find(".//form//field[@name='bridge_account_id']")
    options = ast.literal_eval(field.attrib['options'])
    assert options['no_create'] is True
    assert options['no_create_edit'] is True


def test_eligible_company_bridge_is_kept(transfer):
    company = transfer.company_id
    company.transfer_account_id = Accounts([transfer.bridge_account_id])
    assert transfer._company_bridge_account(company).id == transfer.bridge_account_id.id


@pytest.mark.parametrize('field,value', [
    ('account_type', 'asset_cash'),
    ('account_type', 'expense'),
    ('reconcile', False),
    ('active', False),
    ('company_ids', []),
    ('company_ids', [Record(id=2)]),
])
def test_ineligible_company_bridge_is_not_preselected(transfer, field, value):
    company = transfer.company_id
    company.transfer_account_id = Accounts([transfer.bridge_account_id])
    setattr(transfer.bridge_account_id, field, value)
    result = transfer._company_bridge_account(company)
    assert not result
    assert result.id is False
    # Filtering must not change account type, reconcile setting or company setup.
    assert getattr(transfer.bridge_account_id, field) == value
    assert company.transfer_account_id.id == transfer.bridge_account_id.id


def test_missing_company_bridge_leaves_default_empty(transfer):
    company = transfer.company_id
    company.transfer_account_id = Accounts()
    assert transfer._company_bridge_account(company).id is False
