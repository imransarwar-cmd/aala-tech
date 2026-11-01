"""Odoo database integration tests. Supplied for staging; not run offline."""
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from ..tests_offline.fixtures import workbook


@tagged("post_install", "-at_install")
class TestAttachmentExcelPreview(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.viewer = new_test_user(cls.env, login="dvz_excel_viewer", groups="base.group_user")
        cls.other = new_test_user(cls.env, login="dvz_excel_other", groups="base.group_user")
        cls.portal = new_test_user(cls.env, login="dvz_excel_portal", groups="base.group_portal")
        cls.allowed = cls.env["res.partner"].create({"name": "Preview allowed parent"})
        cls.blocked = cls.env["res.partner"].create({"name": "Preview blocked parent"})
        cls.file = cls.env["ir.attachment"].create({
            "name": "Sample.xlsx", "type": "binary", "raw": workbook(),
            "res_model": "res.partner", "res_id": cls.allowed.id,
        })
        cls.restricted = cls.env["ir.attachment"].create({
            "name": "Restricted.csv", "type": "binary", "raw": b"Code,Value\nSO223,100\n",
            "res_model": "res.partner", "res_id": cls.blocked.id,
        })
        cls.env["ir.rule"].create({
            "name": "Excel preview test: blocked parent",
            "model_id": cls.env["ir.model"]._get_id("res.partner"),
            "domain_force": "[('id', '!=', %s)]" % cls.blocked.id,
            "perm_read": True, "perm_write": False, "perm_create": False, "perm_unlink": False,
        })

    def test_allowed_preview(self):
        result = self.file.with_user(self.viewer).dvz_excel_preview()
        self.assertEqual(result["rows"][0]["cells"][0]["text"], "Hello")

    def test_linked_record_rule_enforced(self):
        with self.assertRaises(AccessError):
            self.restricted.with_user(self.viewer).dvz_excel_preview()

    def test_public_attachment_does_not_bypass_parent(self):
        self.restricted.public = True
        with self.assertRaises(AccessError):
            self.restricted.with_user(self.viewer).dvz_excel_preview()

    def test_portal_blocked(self):
        self.file.public = True
        with self.assertRaises(AccessError):
            self.file.with_user(self.portal).dvz_excel_preview()

    def test_no_attachment_mutation(self):
        before = (self.file.checksum, self.file.raw, self.file.write_date)
        self.file.with_user(self.viewer).dvz_excel_preview()
        self.file.invalidate_recordset()
        self.assertEqual(before, (self.file.checksum, self.file.raw, self.file.write_date))

    def test_foreign_unlinked_file_blocked(self):
        unlinked = self.env["ir.attachment"].with_user(self.viewer).create({
            "name": "Private.csv", "raw": b"A,B\n1,2", "type": "binary",
        })
        with self.assertRaises(AccessError):
            unlinked.with_user(self.other).dvz_excel_preview()

    def test_invalid_page_and_extension(self):
        with self.assertRaises(UserError):
            self.file.with_user(self.viewer).dvz_excel_preview(offset=-1)
        self.file.name = "Sample.xls"
        with self.assertRaises(UserError):
            self.file.with_user(self.viewer).dvz_excel_preview()

    def test_external_link_not_fetched(self):
        link = self.env["ir.attachment"].create({
            "name": "Linked.xlsx", "type": "url", "url": "https://example.invalid/test.xlsx",
            "res_model": "res.partner", "res_id": self.allowed.id,
        })
        with self.assertRaises(UserError):
            link.with_user(self.viewer).dvz_excel_preview()
