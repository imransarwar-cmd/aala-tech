"""Offline regression tests. Odoo ORM is stubbed; NOT live integration tests."""
import ast
import copy
import csv
import importlib.util
import math
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pkg = types.ModuleType('dvz_material_reservation'); pkg.__path__ = [str(ROOT)]
sys.modules[pkg.__name__] = pkg
modpkg = types.ModuleType('dvz_material_reservation.models'); modpkg.__path__ = [str(ROOT / 'models')]
sys.modules[modpkg.__name__] = modpkg
policy = load('dvz_material_reservation.policy', ROOT / 'policy.py')


class AccessError(Exception): pass
class UserError(Exception): pass
class ValidationError(Exception): pass


def compare(a, b, precision_rounding=0.000001):
    diff = a - b
    return 0 if abs(diff) < precision_rounding / 2 else 1 if diff > 0 else -1


def zero(a, precision_rounding=0.000001):
    return abs(a) < precision_rounding / 2


def rounded(a, precision_rounding=0.000001):
    return round(a / precision_rounding) * precision_rounding


class API:
    def __getattr__(self, name):
        if name in ('model', 'model_create_multi'):
            return lambda function: function
        return lambda *args, **kwargs: (lambda function: function)


class Fields:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class UOM:
    def __init__(self, factor=1, rounding=1, id=1):
        self.factor, self.rounding, self.id = factor, rounding, id
    def _compute_quantity(self, value, other, **kwargs):
        return value * self.factor / other.factor


class Lines(list):
    def sorted(self, field, reverse=False):
        return Lines(sorted(self, key=lambda row: getattr(row, field), reverse=reverse))
    def mapped(self, field):
        return [getattr(row, field) for row in self]
    def filtered(self, predicate):
        return Lines(row for row in self if predicate(row))


class Line:
    def __init__(self, row, qty, unit=None, id=None, lot='L1'):
        self.row = row; self.quantity = qty
        self.product_uom_id = unit or row.product_uom
        self.picked = False; self.result_package_id = False; self.is_entire_pack = False
        self.id = id or len(row.move_line_ids) + 1
        self.lot = lot
        row.move_line_ids.append(self)
    def unlink(self):
        self.row.ledger['free'] += self.quantity * self.product_uom_id.factor
        self.row.move_line_ids.remove(self)
    def write(self, vals):
        self.row.ledger['free'] += (self.quantity - vals['quantity']) * self.product_uom_id.factor
        self.quantity = vals['quantity']


class Row:
    def __init__(self, demand=10, qty=0, free=20, limit=None, tracking='none', unit=None):
        self.id = id(self)
        self.product_uom = unit or UOM()
        self.product_id = NS(is_storable=True, tracking=tracking, uom_id=UOM(), id=23)
        self.location_id = NS(usage='internal')
        self.company_id = NS(id=1)
        self.product_uom_qty = demand
        self.state = 'partially_available' if qty else 'confirmed'
        self.picked = False
        self.dvz_reservation_id = NS(id=7, _log_event=lambda *args: self.events.append(args))
        self.dvz_reservation_limit_enabled = limit is not None
        self.dvz_reservation_limit_qty = limit or 0
        self.move_line_ids = Lines()
        self.ledger = {'free': free}
        self.calls = []; self.events = []
        if qty:
            Line(self, qty)
    @property
    def quantity(self):
        return sum(line.product_uom_id._compute_quantity(line.quantity, self.product_uom) for line in self.move_line_ids)


class Env:
    def __init__(self, context=None, permitted=True):
        self.context = context or {}; self.su = False; self.permitted = permitted; self.uid = 7
        self.user = NS(has_group=lambda group: self.permitted)
    def __getitem__(self, model):
        if model == 'dvz.material.reservation':
            return NS(_require_operator=lambda: self.require())
        if model == 'uom.uom':
            return NS(browse=lambda id: self.context.get('unit') if id else False)
        raise AssertionError(model)
    def require(self):
        if not self.permitted:
            raise AccessError('Not permitted')


class Base:
    def __init__(self, rows, env=None):
        object.__setattr__(self, 'rows', rows)
        object.__setattr__(self, 'env', env or Env())
    def __getattribute__(self, key):
        if key.startswith(('dvz_', 'product_', 'quantity', 'state', 'picked', 'location_', 'move_line_ids', 'company_id', 'id')):
            rows = object.__getattribute__(self, 'rows')
            if len(rows) == 1 and hasattr(rows[0], key):
                return getattr(rows[0], key)
        return object.__getattribute__(self, key)
    def __iter__(self):
        return iter([type(self)([row], self.env) for row in self.rows])
    def __bool__(self): return bool(self.rows)
    def __len__(self): return len(self.rows)
    def __sub__(self, other): return type(self)([r for r in self.rows if r not in other.rows], self.env)
    def filtered(self, fn):
        return type(self)([r for r in self.rows if (getattr(type(self)([r], self.env), fn) if isinstance(fn, str) else fn(type(self)([r], self.env)))], self.env)
    def mapped(self, field): return [getattr(r, field) for r in self.rows]
    def ensure_one(self):
        assert len(self.rows) == 1
        return self
    def check_access(self, operation): return None
    def with_context(self, **values):
        return type(self)(self.rows, Env(dict(self.env.context, **values), self.env.permitted))
    def write(self, vals):
        for row in self.rows:
            for key, value in vals.items(): setattr(row, key, value)
        return True
    def _action_assign(self, force_qty=False):
        for row in self.rows:
            if row.state in ('done','cancel') or row.picked: continue
            need = max(row.product_uom_qty - row.quantity, 0) if force_qty is False else force_qty
            take = min(need, row.ledger['free'] / row.product_uom.factor)
            row.calls.append(force_qty)
            row.ledger['free'] -= take * row.product_uom.factor
            if take: Line(row, take)
            row.state = 'assigned' if take >= need else 'partially_available' if row.quantity else 'confirmed'
    def _recompute_state(self):
        for row in self.rows:
            row.state = 'assigned' if row.quantity >= row.product_uom_qty else 'partially_available' if row.quantity else 'confirmed'
    def _do_unreserve(self):
        for row in self.rows:
            for line in list(row.move_line_ids): line.unlink()
        self._recompute_state()
        return True
    def _prepare_move_split_vals(self, qty):
        return {'product_uom_qty': qty}
    def _merge_moves_fields(self):
        return {'product_uom_qty': sum(r.product_uom_qty for r in self.rows)}
    def _prepare_merge_moves_distinct_fields(self): return ['product_id']


odoo = types.ModuleType('odoo')
odoo.api = API(); odoo.fields = Fields(); odoo.models = NS(Model=Base, Constraint=lambda *a: None)
odoo.Command = NS(create=lambda vals: (0, 0, vals))
odoo._ = lambda message, *args: message % args if args else message
sys.modules['odoo'] = odoo
exceptions = types.ModuleType('odoo.exceptions')
exceptions.AccessError=AccessError; exceptions.UserError=UserError; exceptions.ValidationError=ValidationError
sys.modules['odoo.exceptions'] = exceptions
sys.modules['odoo.tools'] = types.ModuleType('odoo.tools')
utils = types.ModuleType('odoo.tools.float_utils')
utils.float_compare=compare; utils.float_is_zero=zero; utils.float_round=rounded
sys.modules[utils.__name__] = utils
stock = load('dvz_material_reservation.models.stock_move', ROOT / 'models/stock_move.py')


class Move(stock.StockMove):
    def _dvz_lock_rows(self):
        for row in self.rows: row.locked_for_test = True


class PolicyTests(unittest.TestCase):
    def test_full_default_target(self): self.assertEqual(policy.effective_target(10), 10)
    def test_limited_target(self): self.assertEqual(policy.effective_target(10, True, 7), 7)
    def test_target_clamped_to_demand(self): self.assertEqual(policy.effective_target(4, True, 7), 4)
    def test_additional_is_not_new_total(self): self.assertEqual(policy.additional_to_reserve(10, 3, True, 7), 4)
    def test_force_is_additional_cap(self): self.assertEqual(policy.additional_to_reserve(10, 3, True, 7, 2), 2)
    def test_force_cannot_exceed_target(self): self.assertEqual(policy.additional_to_reserve(10, 3, True, 7, 99), 4)
    def test_force_zero_means_default_like_odoo(self): self.assertEqual(policy.additional_to_reserve(10,3,True,7,0),4)
    def test_force_none_means_default_like_odoo(self): self.assertEqual(policy.additional_to_reserve(10,3,True,7,None),4)
    def test_release_3_of_10(self): self.assertEqual(policy.release_target(10, 3), 7)
    def test_release_all(self): self.assertEqual(policy.release_target(10, 10), 0)
    def test_excess_release(self):
        with self.assertRaises(ValueError): policy.release_target(4, 5)
    def test_zero_release(self):
        with self.assertRaises(ValueError): policy.release_target(4, 0)
    def test_nonfinite_and_negative(self):
        for value in (float('nan'), float('inf'), float('-inf'), -1):
            with self.subTest(value=value), self.assertRaises(ValueError): policy.finite_nonnegative(value)
    def test_split_cap_not_duplicated(self): self.assertEqual(policy.split_target(10,6,7),3)
    def test_backorder_after_full_target_delivered(self): self.assertEqual(policy.split_target(10,6,4),0)
    def test_finished_current_reservations_zero(self): self.assertEqual(policy.quantity_columns(10,10,finished=True), {'reserved':0,'target':0,'shortage':0,'on_hold':0})
    def test_shortage_separate_from_released(self): self.assertEqual(policy.quantity_columns(10,4,True,7), {'reserved':4,'target':7,'shortage':3,'on_hold':3})
    def test_numerical_invariants(self):
        for demand in range(1,31):
            for target in range(demand+1):
                for split in range(demand+1):
                    new = policy.split_target(demand,target,split)
                    self.assertLessEqual(new, split)
                    self.assertEqual(new + min(target,demand-split),target)


class AssignmentTests(unittest.TestCase):
    def test_standard_untouched(self):
        row=Row(); Move([row])._action_assign(); self.assertEqual(row.quantity,10); self.assertEqual(row.calls,[False])
    def test_limited_adds_only_missing(self):
        row=Row(qty=3,limit=7); Move([row])._action_assign(); self.assertEqual(row.quantity,7); self.assertEqual(row.calls,[4])
    def test_partial_state_recomputed(self):
        row=Row(limit=7); Move([row])._action_assign(); self.assertEqual(row.state,'partially_available')
    def test_zero_target_never_assigns(self):
        row=Row(limit=0); Move([row])._action_assign(); self.assertEqual(row.quantity,0); self.assertEqual(row.calls,[])
    def test_rereserve_cannot_undo_release(self):
        row=Row(qty=7,limit=7); m=Move([row]); m._action_assign(); m._action_assign(); self.assertEqual(row.quantity,7); self.assertEqual(row.calls,[])
    def test_stock_shortage(self):
        row=Row(free=2,limit=7); Move([row])._action_assign(); self.assertEqual(row.quantity,2)
    def test_arriving_stock_fills_only_limit(self):
        row=Row(qty=2,free=10,limit=7); Move([row])._action_assign(); self.assertEqual(row.quantity,7)
    def test_force_is_capped(self):
        row=Row(qty=2,limit=5); Move([row])._action_assign(force_qty=100); self.assertEqual(row.quantity,5)
    def test_done_is_not_assigned(self):
        row=Row(limit=5); row.state='done'; Move([row])._action_assign(); self.assertEqual(row.quantity,0)
    def test_picked_is_not_assigned(self):
        row=Row(limit=5); row.picked=True; Move([row])._action_assign(); self.assertEqual(row.quantity,0)
    def test_mixed_records(self):
        a,b,c=Row(),Row(limit=4),Row(limit=0); Move([a,b,c])._action_assign(); self.assertEqual([r.quantity for r in (a,b,c)],[10,4,0])
    def test_native_move_without_document(self):
        row=Row(limit=0); row.dvz_reservation_id=False; Move([row])._action_assign(); self.assertEqual(row.quantity,10)


class ReleaseTests(unittest.TestCase):
    def test_release_partial_and_cap(self):
        row=Row(qty=10); Move([row])._dvz_set_target(7,'Test','release')
        self.assertEqual(row.quantity,7); self.assertEqual(row.product_uom_qty,10); self.assertEqual(row.dvz_reservation_limit_qty,7)
    def test_released_stock_available_for_other_order(self):
        row=Row(qty=10,free=0); Move([row])._dvz_set_target(7,'Test','release'); self.assertEqual(row.ledger['free'],3)
    def test_release_all_and_recheck(self):
        row=Row(qty=10); m=Move([row]); m._dvz_set_target(0,'Stop','release'); m._action_assign(); self.assertEqual(row.quantity,0)
    def test_resume_part_of_full_release(self):
        row=Row(qty=0,limit=0); Move([row])._dvz_set_target(6,'Resume'); self.assertEqual(row.quantity,6)
    def test_release_retains_lot_identity(self):
        row=Row(); Line(row,4,id=1,lot='KEEP'); Line(row,6,id=2,lot='LAST')
        Move([row])._dvz_set_target(3,'Release','release'); self.assertEqual([(x.lot,x.quantity) for x in row.move_line_ids],[('KEEP',3)])
    def test_uom_conversion_for_partial_release(self):
        row=Row(unit=UOM(12,0.01,4)); Line(row,24,unit=UOM(1,1,1))
        Move([row])._dvz_set_target(1,'One dozen','release'); self.assertEqual(row.quantity,1); self.assertEqual(row.move_line_ids[0].quantity,12)
    def test_incompatible_move_line_rounding_rejected(self):
        row=Row(unit=UOM(12,0.01,4)); Line(row,24,unit=UOM(1,1,1))
        with self.assertRaises(UserError): Move([row])._dvz_set_target(0.1,'Incompatible','release')
    def test_serial_fraction_rejected(self):
        row=Row(qty=2,tracking='serial',unit=UOM(rounding=0.01))
        with self.assertRaises(ValidationError): Move([row])._dvz_set_target(1.5,'Bad','release')
    def test_negative_target_rejected(self):
        row=Row(qty=10)
        with self.assertRaises(ValidationError): Move([row])._dvz_set_target(-1,'Bad')
    def test_excess_target_rejected(self):
        row=Row()
        with self.assertRaises(ValidationError): Move([row])._dvz_set_target(11,'Bad')
    def test_picked_release_rejected(self):
        row=Row(qty=10); row.picked=True
        with self.assertRaises(UserError): Move([row])._dvz_set_target(0,'Bad','release')
    def test_done_release_rejected(self):
        row=Row(qty=10); row.state='done'
        with self.assertRaises(UserError): Move([row])._dvz_set_target(0,'Bad','release')
    def test_permission_required(self):
        row=Row(qty=10)
        with self.assertRaises(AccessError): Move([row],Env(permitted=False))._dvz_set_target(0,'Bad','release')
    def test_rpc_control_write_rejected(self):
        row=Row()
        with self.assertRaises(AccessError): Move([row]).write({'dvz_reservation_limit_qty':99})
    def test_fake_internal_boolean_rejected(self):
        row=Row()
        with self.assertRaises(AccessError): Move([row],Env({'_dvz_material_internal':True})).write({'dvz_reservation_limit_qty':99})
    def test_audit_before_after(self):
        row=Row(qty=10); Move([row])._dvz_set_target(7,'Client postponed','release')
        self.assertEqual(row.events[0][0:2],('release','Client postponed')); self.assertEqual(row.events[0][-2:],(10,7))
    def test_partial_package_rejected(self):
        row=Row(qty=10); row.move_line_ids[0].is_entire_pack=True
        with self.assertRaises(UserError): Move([row])._dvz_set_target(7,'Bad','release')
    def test_full_package_release_supported(self):
        row=Row(qty=10); row.move_line_ids[0].is_entire_pack=True
        Move([row])._dvz_set_target(0,'Full','release'); self.assertEqual(row.quantity,0)
    def test_backorder_uses_remaining_allowance(self):
        row=Row(demand=10,qty=3,limit=6)
        vals=Move([row])._prepare_move_split_vals(7)
        self.assertEqual(vals['dvz_reservation_limit_qty'],3); self.assertEqual(vals['dvz_reservation_id'],7)
    def test_capped_merge_adds_caps(self):
        a,b=Row(demand=10,limit=3),Row(demand=6,limit=2)
        self.assertEqual(Move([a,b])._merge_moves_fields()['dvz_reservation_limit_qty'],5)
    def test_merge_separates_reservations(self):
        fields=Move([])._prepare_merge_moves_distinct_fields(); self.assertIn('dvz_reservation_id',fields)


class CapConstraintTests(unittest.TestCase):
    def test_direct_operation_above_limit_rejected(self):
        row=Row(qty=9,limit=7)
        with self.assertRaises(ValidationError): stock.StockMoveLine._dvz_check_limit(NS(env=Env(),move_id=Move([row])))
    def test_direct_operation_within_limit_allowed(self):
        row=Row(qty=5,limit=7)
        stock.StockMoveLine._dvz_check_limit(NS(env=Env(),move_id=Move([row])))
    def test_merge_cap_checked_after_internal_phase(self):
        row=Row(qty=9,limit=7)
        stock.StockMoveLine._dvz_check_limit(NS(env=Env({'_dvz_material_merging':policy.INTERNAL_TOKEN}),move_id=Move([row])))
        with self.assertRaises(ValidationError): stock.StockMoveLine._dvz_check_limit(NS(env=Env({'_dvz_material_merging':True}),move_id=Move([row])))


class PackageTests(unittest.TestCase):
    def test_manifest_files_exist(self):
        manifest=ast.literal_eval((ROOT/'__manifest__.py').read_text())
        self.assertEqual(manifest['version'],'19.0.1.0.0')
        for file in manifest['data']: self.assertTrue((ROOT/file).is_file(),file)
    def test_all_python_parses(self):
        for file in ROOT.rglob('*.py'): ast.parse(file.read_text(),filename=str(file))
    def test_all_xml_parses(self):
        for file in ROOT.rglob('*.xml'): etree.parse(str(file))
    def test_internal_xml_ids_resolve(self):
        files=[etree.parse(str(f)) for f in ROOT.rglob('*.xml')]
        ids={n.get('id') for tree in files for n in tree.xpath('//*[@id]')}
        models={
            'model_dvz_material_reservation','model_dvz_material_reservation_request','model_dvz_material_reservation_event',
            'model_dvz_reservation_adjust','model_dvz_reservation_adjust_line','model_dvz_reservation_settings',
        }
        for tree in files:
            for node in tree.xpath('//*[@ref]'):
                ref=node.get('ref')
                if '.' not in ref: self.assertIn(ref, ids|models)
    def test_acl_no_global_write_or_event_write(self):
        with (ROOT/'security/ir.model.access.csv').open() as file:
            rows=list(csv.DictReader(file))
        for row in rows:
            self.assertTrue(row['group_id:id'])
            if row['model_id:id']=='model_dvz_material_reservation_event':
                self.assertEqual([row[x] for x in ['perm_write','perm_create','perm_unlink']],['0','0','0'])
    def test_no_direct_quant_or_stock_sql_update(self):
        text='\n'.join(f.read_text() for f in (ROOT/'models').glob('*.py'))
        self.assertNotIn('UPDATE stock_quant',text); self.assertNotIn('_update_reserved_quantity(',text)
    def test_so_view_only_smart_button_and_refresh(self):
        tree=etree.parse(str(ROOT/'views/sale_order_views.xml'))
        self.assertFalse(tree.xpath("//field[@name='project_id' or @name='analytic_account_id']"))
        self.assertEqual(len(tree.xpath('//xpath')),2)
    def test_no_core_module_dependency_on_custom_lock(self):
        manifest=ast.literal_eval((ROOT/'__manifest__.py').read_text())
        self.assertNotIn('dvz_sale_order_lock',manifest['depends'])
    def test_adjustment_is_atomic_no_commit(self):
        text=(ROOT/'wizard/reservation_adjust.py').read_text()
        self.assertNotIn('.commit(',text)
        self.assertLess(text.index('plans.append'),text.index('for move, target in plans'))
    def test_views_use_list_not_legacy_attrs(self):
        for file in ROOT.rglob('*.xml'):
            tree=etree.parse(str(file)); self.assertFalse(tree.xpath('//tree')); self.assertFalse(tree.xpath('//*[@attrs]'))
    def test_searches_group_project_customer_so_product(self):
        tree=etree.parse(str(ROOT/'views/stock_move_views.xml'))
        names=set(tree.xpath('//filter/@name'))
        self.assertTrue({'group_customer','group_project','group_analytic','group_sale','group_product'} <= names)
    def test_unreserve_hook_preserves_zero_limit(self):
        tree=ast.parse((ROOT/'models/stock_move.py').read_text())
        picking=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='StockPicking')
        self.assertTrue(any(isinstance(n,ast.FunctionDef) and n.name=='do_unreserve' for n in picking.body))


if __name__ == '__main__': unittest.main(verbosity=2)
