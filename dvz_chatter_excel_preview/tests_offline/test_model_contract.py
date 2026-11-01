"""Run the actual RPC method with minimal test doubles (NOT an Odoo database)."""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest


class AccessError(Exception): pass
class MissingError(Exception): pass
class UserError(Exception): pass
class PreviewError(Exception): pass

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / 'models/ir_attachment.py').read_text())
classes = ast.Module(body=[n for n in tree.body if isinstance(n, ast.ClassDef)], type_ignores=[])
ns = dict(models=SimpleNamespace(Model=object), _=lambda s: s, AccessError=AccessError,
          MissingError=MissingError, UserError=UserError, PreviewError=PreviewError,
          MAX_FILE_BYTES=100, _logger=logging.getLogger('contract_tests'))
exec(compile(classes, 'ir_attachment_contract.py', 'exec'), ns)
METHOD = ns['IrAttachment'].dvz_excel_preview


class Parent:
    def __init__(self, log, denied=False, exists=True):
        self.log, self.denied, self.present = log, denied, exists
    def browse(self, id): self.log.append('parent_browse'); return self
    def check_access(self, mode):
        self.log.append('parent_read')
        if self.denied: raise AccessError('denied')
    def exists(self): return self.present


class Record:
    def __init__(self, internal=True, denied=False, parent_denied=False):
        self.events, self.denied = [], denied
        self.env = Env(self.events, internal, parent_denied)
        self.type, self.name, self.id = 'binary', 'book.xlsx', 42
        self.res_model, self.res_id, self.file_size = 'parent', 7, 4
        self.present = True
    def ensure_one(self): self.events.append('singleton')
    def check_access(self, mode):
        self.events.append('attachment_read')
        if self.denied: raise AccessError('denied')
    def exists(self): return self.present
    def with_context(self, **kw): self.events.append('context'); return self
    @property
    def raw(self): self.events.append('raw'); return b'data'


class Env(dict):
    def __init__(self, log, internal, parent_denied):
        super().__init__(parent=Parent(log, parent_denied))
        self.user = SimpleNamespace(_is_internal=lambda: internal)


class ModelContractTests(unittest.TestCase):
    def setUp(self):
        ns['build_preview'] = lambda *args, **kw: {'rows': []}

    def test_access_checked_before_contents(self):
        record = Record()
        result = METHOD(record)
        self.assertLess(record.events.index('attachment_read'), record.events.index('raw'))
        self.assertLess(record.events.index('parent_read'), record.events.index('raw'))
        self.assertEqual(result['attachment_id'], 42)

    def test_attachment_denied_before_contents(self):
        r = Record(denied=True)
        with self.assertRaises(AccessError): METHOD(r)
        self.assertNotIn('raw', r.events)

    def test_parent_denied_before_contents(self):
        r = Record(parent_denied=True)
        with self.assertRaises(AccessError): METHOD(r)
        self.assertNotIn('raw', r.events)

    def test_portal_denied_before_contents(self):
        r = Record(internal=False)
        with self.assertRaises(AccessError): METHOD(r)
        self.assertNotIn('raw', r.events)

    def test_missing_parent_model_rejected(self):
        r = Record(); r.res_model = 'missing'
        with self.assertRaises(AccessError): METHOD(r)
        self.assertNotIn('raw', r.events)

    def test_missing_parent_rejected(self):
        r = Record(); r.env['parent'].present = False
        with self.assertRaises(MissingError): METHOD(r)
        self.assertNotIn('raw', r.events)

    def test_missing_attachment_rejected(self):
        r = Record(); r.present = False
        with self.assertRaises(MissingError): METHOD(r)
        self.assertNotIn('raw', r.events)

    def test_link_not_fetched(self):
        r = Record(); r.type = 'url'
        with self.assertRaises(UserError): METHOD(r)
        self.assertNotIn('raw', r.events)

    def test_oversize_rejected_before_raw(self):
        r = Record(); r.file_size = 101
        with self.assertRaises(UserError): METHOD(r)
        self.assertNotIn('raw', r.events)

    def test_unlinked_attachment_still_checks_attachment(self):
        r = Record(); r.res_model, r.res_id = '', 0
        METHOD(r)
        self.assertIn('attachment_read', r.events)
        self.assertNotIn('parent_read', r.events)

    def test_friendly_parser_error(self):
        def reject(*args, **kwargs): raise PreviewError('size limit')
        ns['build_preview'] = reject
        with self.assertRaisesRegex(UserError, 'size limit'): METHOD(Record())

    def test_internal_error_not_exposed(self):
        def reject(*args, **kwargs): raise RuntimeError('private parser detail')
        ns['build_preview'] = reject
        with self.assertLogs('contract_tests', 'WARNING'):
            with self.assertRaises(UserError) as ctx: METHOD(Record())
        self.assertNotIn('private parser detail', str(ctx.exception))


if __name__ == '__main__': unittest.main(verbosity=2)
