"""Live Odoo tests for a disposable database. NOT run in the build container.

Run: odoo-bin -d TEST_DB -i dvz_material_reservation --test-enable \
     --test-tags /dvz_material_reservation --stop-after-init --no-http
"""
from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged, new_test_user


@tagged('post_install', '-at_install')
class TestMaterialReservations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.dvz_auto_material_reservation = True
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.customer = cls.env['res.partner'].create({'name': 'DVZ Reservation Test Customer'})
        cls.product = cls.env['product.product'].create({
            'name': 'DVZ Test Controller', 'type': 'consu', 'is_storable': True, 'list_price': 100,
        })
        cls.env['stock.quant']._update_available_quantity(cls.product, cls.warehouse.lot_stock_id, 20)

    def _sale(self, qty=10):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id, 'company_id': self.company.id,
            'warehouse_id': self.warehouse.id,
            'order_line': [Command.create({'product_id': self.product.id,
                'product_uom_qty': qty, 'price_unit': 100})],
        })
        order.action_confirm()
        reservation = self.env['dvz.material.reservation'].search([('sale_order_id', '=', order.id)])
        return order, reservation, reservation.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))

    def _manual(self, qty=5, project=False):
        doc = self.env['dvz.material.reservation'].create({
            'company_id': self.company.id, 'partner_id': self.customer.id,
            'warehouse_id': self.warehouse.id, 'location_id': self.warehouse.lot_stock_id.id,
            'project_id': project.id if project else False,
            'request_line_ids': [Command.create({'product_id': self.product.id, 'quantity': qty})],
        })
        doc.action_confirm_manual()
        return doc

    def _adjust(self, move, mode='release', quantity=0, all=False):
        wizard = self.env['dvz.reservation.adjust'].create({
            'company_id': self.company.id, 'mode': mode, 'release_all': all, 'reason': 'Test change',
            'line_ids': [Command.create({'move_id': move.id, 'quantity': quantity})],
        })
        wizard.action_apply()

    def test_01_so_confirmation_reserves(self):
        order, doc, move = self._sale()
        self.assertEqual(len(doc), 1)
        self.assertEqual(move.dvz_reserved_qty, 10)
        self.assertEqual(doc.sale_order_id, order)
        self.assertEqual(doc.partner_id, self.customer)

    def test_02_manual_without_project(self):
        doc = self._manual()
        self.assertFalse(doc.project_id)
        self.assertFalse(doc.sale_order_id)
        self.assertEqual(doc.move_ids.dvz_reserved_qty, 5)
        self.assertNotEqual(doc.manual_picking_id.state, 'done')

    def test_03_partial_release_preserves_order_and_move_demand(self):
        order, doc, move = self._sale()
        self._adjust(move, quantity=3)
        self.assertEqual(move.dvz_reserved_qty, 7)
        self.assertEqual(move.product_uom_qty, 10)
        self.assertEqual(order.order_line.product_uom_qty, 10)
        self.assertEqual(move.dvz_reservation_limit_qty, 7)

    def test_04_check_availability_does_not_retake_released_stock(self):
        order, doc, move = self._sale()
        self._adjust(move, quantity=3)
        move.picking_id.action_assign()
        self.assertEqual(move.dvz_reserved_qty, 7)

    def test_05_full_release_and_target_resume(self):
        order, doc, move = self._sale()
        self._adjust(move, all=True)
        move.picking_id.action_assign()
        self.assertEqual(move.dvz_reserved_qty, 0)
        self.assertEqual(doc.state, 'released')
        self._adjust(move, mode='target', quantity=4)
        self.assertEqual(move.dvz_reserved_qty, 4)

    def test_06_shortage_not_fake_stock(self):
        order, doc, move = self._sale(25)
        self.assertEqual(move.dvz_reserved_qty, 20)
        self.assertEqual(move.dvz_shortage_qty, 5)

    def test_07_another_order_cannot_take_reserved_quantity(self):
        first, doc1, move1 = self._sale(15)
        second, doc2, move2 = self._sale(10)
        self.assertEqual(move1.dvz_reserved_qty, 15)
        self.assertEqual(move2.dvz_reserved_qty, 5)
        self.assertEqual(move2.dvz_shortage_qty, 5)

    def test_08_released_stock_can_go_to_other_customer(self):
        first, doc1, move1 = self._sale(20)
        self._adjust(move1, quantity=4)
        second, doc2, move2 = self._sale(4)
        self.assertEqual(move1.dvz_reserved_qty, 16)
        self.assertEqual(move2.dvz_reserved_qty, 4)

    def test_09_excess_release_rejected_and_unchanged(self):
        order, doc, move = self._sale()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._adjust(move, quantity=11)
        self.assertEqual(move.dvz_reserved_qty, 10)

    def test_10_picked_release_rejected(self):
        order, doc, move = self._sale()
        move.picked = True
        with self.assertRaises(UserError), self.cr.savepoint():
            self._adjust(move, all=True)

    def test_11_completed_delivery_cannot_be_unreserved(self):
        order, doc, move = self._sale()
        move.picked = True
        move._action_done()
        self.assertEqual(move.dvz_reserved_qty, 0)
        with self.assertRaises(UserError), self.cr.savepoint():
            self._adjust(move, all=True)

    def test_12_partial_delivery_backorder_cap(self):
        order, doc, move = self._sale()
        self._adjust(move, quantity=4)  # demand 10, target 6
        move.quantity = 3
        move.picked = True
        move._action_done()
        backorder = doc.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
        self.assertEqual(len(backorder), 1)
        self.assertEqual(backorder.product_uom_qty, 7)
        self.assertEqual(backorder.dvz_reservation_limit_qty, 3)
        self.assertLessEqual(backorder.quantity, 3)

    def test_13_manual_cancel_frees_stock_not_delivery(self):
        doc = self._manual()
        doc.action_cancel_manual()
        self.assertEqual(doc.state, 'cancel')
        self.assertEqual(doc.move_ids.dvz_reserved_qty, 0)
        self.assertEqual(doc.manual_picking_id.state, 'cancel')

    def test_14_no_duplicate_reservations_on_refresh(self):
        order, doc, move = self._sale()
        order.action_dvz_sync_material_reservations()
        self.assertEqual(self.env['dvz.material.reservation'].search_count([('sale_order_id','=',order.id)]), 1)
        self.assertEqual(move.dvz_reserved_qty, 10)

    def test_15_reservation_audit_readonly(self):
        order, doc, move = self._sale()
        self._adjust(move, quantity=2)
        event = doc.event_ids.filtered(lambda e: e.action == 'release')
        self.assertEqual(event.reserved_before, 10)
        self.assertEqual(event.reserved_after, 8)
        with self.assertRaises(AccessError): event.write({'reason': 'Changed'})

    def test_16_serial_fraction_rejected(self):
        serial_product = self.env['product.product'].create({
            'name': 'DVZ Test Serial', 'type': 'consu', 'is_storable': True, 'tracking': 'serial'})
        doc = self.env['dvz.material.reservation']
        with self.assertRaises(ValidationError), self.cr.savepoint():
            doc.create({'partner_id': self.customer.id, 'warehouse_id': self.warehouse.id,
                'request_line_ids': [Command.create({'product_id': serial_product.id, 'quantity': 1.5})]})

    def test_17_manual_project_link(self):
        project = self.env['project.project'].create({'name':'DVZ Reservation Test Project','company_id':self.company.id})
        doc = self._manual(project=project)
        self.assertEqual(doc.project_id, project)
        self.assertEqual(doc.move_ids.dvz_project_id, project)

    def test_18_native_unreserve_respects_release_policy(self):
        order, doc, move = self._sale()
        move.picking_id.do_unreserve()
        move.picking_id.action_assign()
        self.assertEqual(move.dvz_reserved_qty, 0)
        self.assertEqual(move.dvz_reservation_limit_qty, 0)

    def test_19_nonoperator_cannot_release(self):
        order, doc, move = self._sale()
        user = new_test_user(self.env, login='dvz_test_stock_reader', groups='stock.group_stock_user')
        with self.assertRaises(AccessError):
            move.with_user(user).action_dvz_release()

    def test_20_no_service_reservation(self):
        service = self.env['product.product'].create({'name': 'DVZ Test Service', 'type': 'service'})
        order = self.env['sale.order'].create({'partner_id': self.customer.id, 'warehouse_id': self.warehouse.id,
            'order_line': [Command.create({'product_id': service.id, 'product_uom_qty': 1})]})
        order.action_confirm()
        self.assertFalse(self.env['dvz.material.reservation'].search([('sale_order_id','=',order.id)]))
