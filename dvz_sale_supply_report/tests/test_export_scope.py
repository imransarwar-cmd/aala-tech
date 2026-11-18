"""Regression tests for mandatory-SO, complete-product exports.

Run through Odoo's module test runner. These tests require an Odoo database;
syntax compilation in the build workspace is not an integration test run.
"""

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSaleSupplyExportScope(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.unit = cls.env.ref("uom.product_uom_unit")
        cls.customer = cls.env["res.partner"].create({"name": "SO Export Scope Customer"})
        cls.other_customer = cls.env["res.partner"].create({"name": "Other Export Customer"})
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "SO Export Scope Prices",
            "currency_id": cls.company.currency_id.id,
            "company_id": cls.company.id,
        })
        cls.products = cls.env["product.product"].create([
            {"name": "Scope Controller", "type": "consu", "uom_id": cls.unit.id},
            {"name": "Scope Sensor", "type": "consu", "uom_id": cls.unit.id},
        ])
        cls.order_a = cls._create_order([
            (cls.products[0], 8), (cls.products[1], 3), (cls.products[0], 2),
        ])
        cls.product_lines_a = cls.order_a.order_line
        cls.env["sale.order.line"].create({
            "order_id": cls.order_a.id,
            "display_type": "line_note",
            "name": "This note is not a product detail row.",
        })
        cls.order_b = cls._create_order([(cls.products[1], 5)])
        cls.unrelated_order = cls._create_order([(cls.products[0], 99)])

    @classmethod
    def _create_order(cls, specifications):
        return cls.env["sale.order"].create({
            "partner_id": cls.customer.id,
            "company_id": cls.company.id,
            "pricelist_id": cls.pricelist.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "name": product.name,
                "product_uom_id": cls.unit.id,
                "product_uom_qty": quantity,
                "price_unit": 10,
                "tax_ids": [Command.clear()],
            }) for product, quantity in specifications],
        })

    def _wizard(self, orders, **extra_values):
        values = {
            "order_ids": [Command.set(orders.ids)],
            "company_ids": [Command.set(self.company.ids)],
        }
        values.update(extra_values)
        return self.env["dvz.sale.supply.export"].create(values)

    def _wizard_from_context(self, **context):
        model = self.env["dvz.sale.supply.export"].with_context(**context)
        values = model.default_get(["order_ids", "company_ids"])
        return model.create(values)

    def test_missing_so_cannot_export_even_with_legacy_selected_lines(self):
        self.assertTrue(self.env["dvz.sale.supply.export"]._fields["order_ids"].required)
        # An unsaved record also exercises the export guard independently of
        # create-time constraints and required-field validation in the UI.
        wizard = self.env["dvz.sale.supply.export"].new({
            "company_ids": [Command.set(self.company.ids)],
            "scope": "selected",
            "sale_line_ids": [Command.set(self.product_lines_a[:1].ids)],
        })
        with self.assertRaises((UserError, ValidationError)):
            wizard._get_report_lines()

    def test_one_so_exports_every_product_and_preserves_duplicate_lines(self):
        lines = self._wizard(self.order_a)._get_report_lines()
        self.assertEqual(set(lines.ids), set(self.product_lines_a.ids))
        self.assertEqual(len(lines), 3)
        self.assertEqual(len(lines.filtered(lambda line: line.product_id == self.products[0])), 2)
        self.assertFalse(lines.filtered("display_type"))

    def test_selected_product_row_prefills_so_and_exports_all_siblings(self):
        wizard = self._wizard_from_context(
            active_model="sale.order.line", active_ids=self.product_lines_a[:1].ids,
        )
        self.assertEqual(wizard.order_ids, self.order_a)
        self.assertEqual(set(wizard._get_report_lines().ids), set(self.product_lines_a.ids))

    def test_sale_order_context_prefills_selected_orders(self):
        orders = self.order_a | self.order_b
        wizard = self._wizard_from_context(active_model="sale.order", active_ids=orders.ids)
        self.assertEqual(set(wizard.order_ids.ids), set(orders.ids))

    def test_multiple_sos_include_all_their_lines_and_exclude_unrelated_order(self):
        orders = self.order_a | self.order_b
        lines = self._wizard(orders)._get_report_lines()
        expected = self.product_lines_a | self.order_b.order_line
        self.assertEqual(set(lines.ids), set(expected.ids))
        self.assertNotIn(self.unrelated_order.id, lines.order_id.ids)

    def test_legacy_filters_cannot_remove_selected_so_product_details(self):
        wizard = self._wizard(
            self.order_a,
            scope="selected",
            sale_line_ids=[Command.set(self.product_lines_a[:1].ids)],
            product_ids=[Command.set(self.products[1].ids)],
            customer_id=self.other_customer.id,
            date_from="2100-01-01", date_to="2100-12-31",
            include_quotations=False, include_cancelled=False,
        )
        self.assertEqual(self.order_a.state, "draft")
        self.assertEqual(set(wizard._get_report_lines().ids), set(self.product_lines_a.ids))

    def test_explicit_order_defaults_take_priority_over_selected_line_context(self):
        wizard = self._wizard_from_context(
            default_order_ids=[Command.set(self.order_b.ids)],
            active_model="sale.order.line", active_ids=self.product_lines_a[:1].ids,
        )
        self.assertEqual(wizard.order_ids, self.order_b)
        self.assertEqual(set(wizard._get_report_lines().ids), set(self.order_b.order_line.ids))
