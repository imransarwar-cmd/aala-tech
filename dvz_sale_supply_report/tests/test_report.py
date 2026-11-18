"""Odoo integration cases; run with a disposable Odoo 19 test database.

These exercise native order, reservation, delivery and return behavior.  They
are deliberately separate from the framework-independent quantity tests.
"""

from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestSaleSupplyReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.unit = cls.env.ref("uom.product_uom_unit")
        cls.partner = cls.env["res.partner"].create({"name": "Supply Report Test Customer"})
        cls.warehouse = cls.env["stock.warehouse"].create({
            "name": "Supply Report Test Warehouse",
            "code": "DVZSR",
            "company_id": cls.company.id,
            "delivery_steps": "ship_only",
        })
        cls.warehouse.out_type_id.reservation_method = "at_confirm"
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Supply Report Test Prices",
            "currency_id": cls.company.currency_id.id,
            "company_id": cls.company.id,
        })
        cls.products = cls.env["product.product"].create([
            {
                "name": "Supply Report Controller",
                "default_code": "DVZ-CTRL",
                "type": "consu", "is_storable": True,
                "uom_id": cls.unit.id, "list_price": 100,
            },
            {
                "name": "Supply Report Sensor",
                "default_code": "DVZ-SENS",
                "type": "consu", "is_storable": True,
                "uom_id": cls.unit.id, "list_price": 25,
            },
        ])
        cls.product = cls.products[0]
        cls.other_product = cls.products[1]
        cls.manager = new_test_user(
            cls.env, login="dvz_supply_test_manager",
            groups="base.group_user,sales_team.group_sale_manager,"
                   "stock.group_stock_manager,purchase.group_purchase_manager",
            company_id=cls.company.id,
        )
        cls.salesperson = new_test_user(
            cls.env, login="dvz_supply_test_salesperson",
            groups="base.group_user,sales_team.group_sale_salesman",
            company_id=cls.company.id,
        )

    def _make_order(self, specifications=None):
        specifications = specifications or [(self.product, 8)]
        return self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "company_id": self.company.id,
            "warehouse_id": self.warehouse.id,
            "pricelist_id": self.pricelist.id,
            "user_id": self.salesperson.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "name": product.name,
                "product_uom_id": self.unit.id,
                "product_uom_qty": quantity,
                "price_unit": product.list_price,
                "tax_ids": [Command.clear()],
            }) for product, quantity in specifications],
        })

    def _stock(self, quantity, product=None):
        return self.env["stock.quant"]._update_available_quantity(
            product or self.product, self.warehouse.lot_stock_id, quantity)

    def _record_split(self, line, **changes):
        values = {
            "stock_plan": 6, "purchase_plan": 2,
            "stock_used": 0, "purchase_used": 0,
            "note": "Opening stock 6; new purchase requirement 2.",
            "purchase_lines": self.env["purchase.order.line"],
        }
        values.update(changes)
        return line.with_user(self.manager)._dvz_apply_source_split(**values)

    def _deliver(self, line, quantity):
        moves, _returns = line._get_outgoing_incoming_moves()
        move = moves.filtered(lambda m: m.state not in ("done", "cancel"))
        self.assertEqual(len(move), 1, "Test fixture expects one open customer delivery")
        move.write({"quantity": quantity, "picked": True})
        return move._action_done(cancel_backorder=False)

    def _return(self, delivery, quantity):
        picking = delivery.picking_id
        wizard = Form(self.env["stock.return.picking"].with_context(
            active_id=picking.id,
            active_ids=picking.ids,
            active_model="stock.picking",
        )).save()
        return_line = wizard.product_return_moves.filtered(
            lambda item: item.move_id in delivery)
        self.assertEqual(len(return_line), 1)
        return_line.write({"quantity": quantity, "to_refund": True})
        result = wizard.action_create_returns()
        returned_picking = self.env["stock.picking"].browse(result["res_id"])
        returned_picking.move_ids.write({"quantity": quantity, "picked": True})
        returned_picking.move_ids._action_done(cancel_backorder=False)
        return returned_picking

    def test_each_product_and_repeated_product_keeps_its_own_row(self):
        order = self._make_order([
            (self.product, 8), (self.other_product, 3), (self.product, 2)])
        product_lines = order.order_line
        self.env["sale.order.line"].create({
            "order_id": order.id, "display_type": "line_note",
            "name": "A note must not become a product report row.",
        })
        action = order.action_dvz_supply_report()
        self.assertEqual(action["res_model"], "sale.order.line")
        report_lines = self.env["sale.order.line"].search(action["domain"])
        self.assertEqual(set(report_lines.ids), set(product_lines.ids))
        self.assertEqual(len(report_lines), 3)
        self.assertEqual(len(report_lines.filtered(lambda line: line.product_id == self.product)), 2)

    def test_eight_required_six_stock_two_purchase_does_not_move_inventory(self):
        self._stock(6)
        order = self._make_order()
        line = order.order_line
        before_moves = self.env["stock.move"].search_count([("sale_line_id", "=", line.id)])
        before_stock = self.product.with_context(warehouse_id=self.warehouse.id).qty_available
        self._record_split(line)
        self.assertTrue(line.dvz_source_override)
        self.assertEqual(line.dvz_stock_qty, 6)
        self.assertEqual(line.dvz_purchase_qty, 2)
        self.assertEqual(line.dvz_total_source_qty, 8)
        self.assertEqual(line.dvz_shortage_qty, 0)
        self.assertEqual(line.dvz_pending_qty, 8)
        self.assertEqual(line.dvz_stock_used_qty, 0)
        self.assertEqual(line.dvz_purchase_used_qty, 0)
        self.assertEqual(line.dvz_source_updated_by, self.manager)
        self.assertFalse(line.dvz_po_refs, "An unlinked sourcing declaration must not invent a PO")
        self.assertEqual(self.env["stock.move"].search_count([("sale_line_id", "=", line.id)]), before_moves)
        self.assertEqual(self.product.with_context(warehouse_id=self.warehouse.id).qty_available, before_stock)

    def test_native_reservation_six_is_not_fabricated_as_purchase_two(self):
        self._stock(6)
        order = self._make_order()
        order.action_confirm()
        order.picking_ids.action_assign()
        line = order.order_line
        self.assertEqual(line.qty_delivered, 0)
        self.assertEqual(line.dvz_reserved_qty, 6)
        self.assertEqual(line.dvz_pending_qty, 8)
        self.assertEqual(line.dvz_stock_qty, 0, "A reservation does not prove pre-order stock origin")
        self.assertEqual(line.dvz_purchase_qty, 0, "A shortage does not create a purchase order")
        self.assertEqual(line.dvz_total_source_qty, 0)
        self.assertEqual(line.dvz_shortage_qty, 8)

    def test_partial_delivery_backorder_and_return_follow_native_net_delivery(self):
        self._stock(8)
        order = self._make_order()
        order.action_confirm()
        line = order.order_line
        delivered = self._deliver(line, 6)
        self.assertEqual(line.qty_delivered, 6)
        self.assertEqual(line.dvz_pending_qty, 2)
        self.assertEqual(line.dvz_unclassified_used_qty, 6)
        self.assertEqual(line.dvz_purchase_used_qty, 0)
        self._return(delivered, 2)
        self.assertEqual(line.qty_delivered, 4)
        self.assertEqual(line.dvz_pending_qty, 4)
        self.assertEqual(line.dvz_unclassified_used_qty, 4)

    def test_manual_delivered_split_and_stale_return_are_visible(self):
        self._stock(8)
        order = self._make_order()
        order.action_confirm()
        line = order.order_line
        delivered = self._deliver(line, 8)
        self._record_split(line, stock_used=6, purchase_used=2)
        self.assertEqual(line.dvz_stock_used_qty, 6)
        self.assertEqual(line.dvz_purchase_used_qty, 2)
        self.assertEqual(line.dvz_unclassified_used_qty, 0)
        self._return(delivered, 2)
        self.assertEqual(line.qty_delivered, 6)
        self.assertIn("Review required", line.dvz_source_basis)
        self.assertIn("Quantities changed", line.dvz_source_basis)

    def test_delivery_change_requires_review_of_recorded_split(self):
        self._stock(8)
        order = self._make_order()
        order.action_confirm()
        line = order.order_line
        self._record_split(line)
        self._deliver(line, 6)
        self.assertEqual(line.qty_delivered, 6)
        self.assertEqual(line.dvz_stock_used_qty, 0, "Source usage is not invented from a plan")
        self.assertEqual(line.dvz_unclassified_used_qty, 6)
        self.assertIn("Quantities changed", line.dvz_source_basis)

    def test_order_quantity_and_product_changes_flag_stale_source(self):
        line = self._make_order().order_line
        self._record_split(line)
        line.product_uom_qty = 9
        self.assertEqual(line.dvz_shortage_qty, 1)
        self.assertIn("Quantities changed", line.dvz_source_basis)
        line.product_id = self.other_product
        self.assertIn("product/unit changed", line.dvz_source_basis)
        self.assertEqual(line.dvz_stock_qty, 0)
        self.assertEqual(line.dvz_purchase_qty, 0)
        self.assertEqual(line.dvz_shortage_qty, 9)

    def test_invalid_splits_and_missing_evidence_are_rejected(self):
        line = self._make_order().order_line
        invalid_values = [
            {"stock_plan": -1},
            {"purchase_plan": -1},
            {"stock_plan": 7, "purchase_plan": 2},
            {"stock_used": 1},
            {"note": "   "},
        ]
        for changes in invalid_values:
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError), self.cr.savepoint():
                    self._record_split(line, **changes)

    def test_nonmanager_cannot_record_clear_or_directly_write_source(self):
        line = self._make_order().order_line
        ordinary_line = line.with_user(self.salesperson)
        with self.assertRaises(AccessError):
            ordinary_line._dvz_apply_source_split(6, 2, 0, 0, "Not authorized")
        with self.assertRaises(AccessError):
            ordinary_line.action_dvz_clear_source_split()
        with self.assertRaises(AccessError):
            ordinary_line.write({"dvz_manual_stock_qty": 6})
        with self.assertRaises(AccessError):
            self.env["sale.order.line"].with_user(self.salesperson).create({
                "order_id": line.order_id.id,
                "product_id": self.product.id,
                "name": self.product.name,
                "product_uom_id": self.unit.id,
                "product_uom_qty": 8,
                "price_unit": 100,
                "dvz_manual_stock_qty": 6,
            })

    def test_manager_direct_write_validates_and_clear_restores_unknown_source(self):
        line = self._make_order().order_line
        self._record_split(line)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            line.with_user(self.manager).write({"dvz_manual_stock_qty": -1})
        line.with_user(self.manager).action_dvz_clear_source_split()
        self.assertFalse(line.dvz_source_override)
        self.assertEqual(line.dvz_total_source_qty, 0)
        self.assertEqual(line.dvz_shortage_qty, 8)
        self.assertEqual(line.product_uom_qty, 8)

    def _purchase_chain(self, receipt_quantity=8, shared=False):
        """Build real receipts and deliveries without an MTO procurement route."""
        order = self._make_order()
        order.action_confirm()
        line = order.order_line
        outgoing, _returns = line._get_outgoing_incoming_moves()
        if shared:
            other_order = self._make_order()
            other_order.action_confirm()
            other_outgoing, _returns = other_order.order_line._get_outgoing_incoming_moves()
            outgoing |= other_outgoing
        purchase = self.env["purchase.order"].create({
            "partner_id": self.partner.id,
            "company_id": self.company.id,
            "currency_id": self.company.currency_id.id,
            "picking_type_id": self.warehouse.in_type_id.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "name": self.product.name,
                "product_qty": receipt_quantity,
                "product_uom_id": self.unit.id,
                "price_unit": 10,
                "date_planned": fields.Datetime.now(),
                "tax_ids": [Command.clear()],
            })],
        })
        purchase.button_confirm()
        purchase_line = purchase.order_line
        receipt = purchase_line.move_ids.filtered(lambda move: move.state != "cancel")
        self.assertEqual(len(receipt), 1)
        receipt.write({
            "move_dest_ids": [Command.set(outgoing.ids)],
            "quantity": receipt_quantity,
            "picked": True,
        })
        receipt._action_done(cancel_backorder=False)
        delivered = self._deliver(line, 8)
        # Use explicit ordered timestamps, independent of test-runner speed.
        delivered.date = fields.Datetime.now()
        receipt.date = delivered.date - timedelta(hours=1)
        return line, receipt, delivered, purchase_line

    def test_exclusive_purchase_receipt_is_proven_purchase_delivery(self):
        line, receipt, delivered, purchase_line = self._purchase_chain()
        self.assertEqual(
            line._dvz_exact_purchase_line(delivered, 8, done=True), purchase_line)
        planned, used, references, restricted = line._dvz_auto_purchase_source()
        self.assertEqual(planned, 8)
        self.assertEqual(used, 8)
        self.assertIn(purchase_line.order_id.name, references)
        self.assertFalse(restricted)
        self.assertLess(receipt.date, delivered.date)

    def test_shared_purchase_receipt_does_not_fabricate_per_order_allocation(self):
        line, receipt, delivered, _purchase_line = self._purchase_chain(
            receipt_quantity=16, shared=True)
        self.assertEqual(len(receipt.move_dest_ids), 2)
        self.assertFalse(line._dvz_exact_purchase_line(delivered, 8, done=True))
        planned, used, references, restricted = line._dvz_auto_purchase_source()
        self.assertEqual((planned, used, references, restricted), (0, 0, "", False))

    def test_receipt_two_cannot_prove_purchase_delivery_of_eight(self):
        line, receipt, delivered, _purchase_line = self._purchase_chain(receipt_quantity=2)
        self.assertEqual(receipt.quantity, 2)
        self.assertEqual(delivered.quantity, 8)
        self.assertFalse(line._dvz_exact_purchase_line(delivered, 8, done=True))
        planned, used, references, restricted = line._dvz_auto_purchase_source()
        self.assertEqual((planned, used, references, restricted), (0, 0, "", False))

    def test_purchase_received_after_delivery_cannot_be_its_proven_source(self):
        line, receipt, delivered, _purchase_line = self._purchase_chain()
        receipt.date = delivered.date + timedelta(hours=1)
        self.assertFalse(line._dvz_exact_purchase_line(delivered, 8, done=True))
        planned, used, references, restricted = line._dvz_auto_purchase_source()
        self.assertEqual((planned, used, references, restricted), (0, 0, "", False))

    def test_nonmanager_cannot_set_protected_source_through_context_defaults(self):
        order = self._make_order()
        model = self.env["sale.order.line"].with_user(self.salesperson).with_context(
            default_dvz_source_override=True,
            default_dvz_manual_stock_qty=6,
            default_dvz_manual_purchase_qty=2,
        )
        with self.assertRaises(AccessError):
            model.create({
                "order_id": order.id,
                "product_id": self.product.id,
                "name": self.product.name,
                "product_uom_id": self.unit.id,
                "product_uom_qty": 8,
                "price_unit": 100,
            })

    def test_portal_user_cannot_discover_internal_source_fields(self):
        portal = new_test_user(
            self.env, login="dvz_supply_test_portal", groups="base.group_portal",
            company_id=self.company.id,
        )
        exposed = self.env["sale.order.line"].with_user(portal).fields_get(attributes=["string"])
        self.assertFalse([name for name in exposed if name.startswith("dvz_")])
