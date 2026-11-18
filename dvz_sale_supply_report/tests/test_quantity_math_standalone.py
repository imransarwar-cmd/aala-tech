"""Run with: python3 tests/test_quantity_math_standalone.py.

The module is loaded directly so these numerical tests do not need Odoo.
Odoo-specific access, stock, and procurement behavior requires integration
tests on an Odoo 19 database and is not claimed by this test suite.
"""

import importlib.util
import math
from pathlib import Path
import unittest


HELPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "quantity_math.py"
)
SPEC = importlib.util.spec_from_file_location("quantity_math_under_test", HELPER_PATH)
quantity_math = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quantity_math)


class QuantityMathTests(unittest.TestCase):
    def reconcile(self, ordered=8, delivered=0, stock_plan=6, purchase_plan=2,
                  stock_used=0, purchase_used=0, precision=1e-6):
        return quantity_math.reconcile_source_quantities(
            ordered, delivered, stock_plan, purchase_plan, stock_used,
            purchase_used, precision=precision,
        )

    def test_user_eight_split_six_stock_two_purchase(self):
        result = self.reconcile(delivered=8, stock_used=6, purchase_used=2)
        self.assertEqual(result, {
            "pending_qty": 0.0,
            "overdelivered_qty": 0.0,
            "total_source_qty": 8.0,
            "shortage_qty": 0.0,
            "unclassified_used_qty": 0.0,
        })
        self.assertIsNone(quantity_math.validate_manual_split(8, 8, 6, 2, 6, 2))

    def test_partial_delivery_does_not_consume_planned_purchase(self):
        result = self.reconcile(delivered=4, stock_used=4)
        self.assertEqual(result["pending_qty"], 4)
        self.assertEqual(result["total_source_qty"], 8)
        self.assertEqual(result["shortage_qty"], 0)
        self.assertEqual(result["unclassified_used_qty"], 0)

    def test_missing_purchase_is_shortage_not_purchase_supply(self):
        result = self.reconcile(purchase_plan=0)
        self.assertEqual(result["total_source_qty"], 6)
        self.assertEqual(result["shortage_qty"], 2)
        self.assertEqual(result["pending_qty"], 8)

    def test_unclassified_historical_delivery_remains_visible(self):
        result = self.reconcile(delivered=8, stock_plan=0, purchase_plan=0)
        self.assertEqual(result["unclassified_used_qty"], 8)
        self.assertEqual(result["total_source_qty"], 0)

    def test_fractional_uom_quantities_are_not_rounded_to_whole_units(self):
        result = self.reconcile(
            ordered=2.75, delivered=1.25, stock_plan=1.5, purchase_plan=0.5,
            stock_used=1, purchase_used=0.25,
        )
        self.assertEqual(result["pending_qty"], 1.5)
        self.assertEqual(result["total_source_qty"], 2)
        self.assertEqual(result["shortage_qty"], 0.75)
        self.assertEqual(result["unclassified_used_qty"], 0)

    def test_floating_point_noise_is_tolerated(self):
        result = self.reconcile(
            ordered=0.3, delivered=0.1 + 0.2,
            stock_plan=0.1, purchase_plan=0.2,
            stock_used=0.1, purchase_used=0.2,
        )
        self.assertEqual(result["overdelivered_qty"], 0)
        self.assertEqual(result["pending_qty"], 0)
        self.assertEqual(result["shortage_qty"], 0)
        self.assertEqual(quantity_math.manual_split_warnings(
            0.3, 0.3, 0.1, 0.2, 0.1, 0.2,
        ), [])

    def test_normalization_preserves_material_negative_values(self):
        self.assertEqual(quantity_math.normalize_quantity(-1e-8), 0)
        self.assertEqual(quantity_math.normalize_quantity(-2.5), -2.5)

    def test_overdelivery_is_visible_and_can_have_source_coverage(self):
        result = self.reconcile(
            ordered=8, delivered=10, stock_plan=6, purchase_plan=4,
            stock_used=6, purchase_used=4,
        )
        self.assertEqual(result["overdelivered_qty"], 2)
        self.assertEqual(result["pending_qty"], 0)
        self.assertEqual(quantity_math.manual_split_warnings(8, 10, 6, 4, 6, 4), [])

    def test_each_negative_manual_field_is_rejected(self):
        for index in range(2, 6):
            values = [8, 8, 6, 2, 6, 2]
            values[index] = -1
            with self.subTest(index=index):
                with self.assertRaisesRegex(ValueError, "negative"):
                    quantity_math.validate_manual_split(*values)

    def test_plan_above_order_and_delivery_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Total planned"):
            quantity_math.validate_manual_split(8, 0, 6, 3, 0, 0)

    def test_used_total_above_actual_delivery_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Total used"):
            quantity_math.validate_manual_split(8, 4, 6, 2, 4, 1)

    def test_each_used_source_is_limited_by_its_own_plan(self):
        for values, message in (
            ((8, 8, 2, 6, 3, 5), "Used stock"),
            ((8, 8, 6, 2, 5, 3), "Used purchase"),
        ):
            with self.subTest(values=values):
                with self.assertRaisesRegex(ValueError, message):
                    quantity_math.validate_manual_split(*values)

    def test_reduced_so_quantity_warns_without_blocking_report(self):
        result = self.reconcile(ordered=5, delivered=0)
        self.assertEqual(result["total_source_qty"], 8)
        self.assertEqual(result["shortage_qty"], 0)
        issues = quantity_math.manual_split_warnings(5, 0, 6, 2, 0, 0)
        self.assertTrue(any("Total planned" in issue for issue in issues))

    def test_customer_return_exposes_stale_used_split(self):
        result = self.reconcile(delivered=6, stock_used=6, purchase_used=2)
        self.assertEqual(result["pending_qty"], 2)
        self.assertEqual(result["unclassified_used_qty"], 0)
        issues = quantity_math.manual_split_warnings(8, 6, 6, 2, 6, 2)
        self.assertTrue(any("Total used" in issue for issue in issues))

    def test_negative_net_delivery_is_preserved_and_flagged(self):
        result = self.reconcile(delivered=-2)
        self.assertEqual(result["pending_qty"], 10)
        self.assertEqual(result["unclassified_used_qty"], 0)
        issues = quantity_math.manual_split_warnings(8, -2, 6, 2, 0, 0)
        self.assertTrue(any("returns exceed deliveries" in issue for issue in issues))

    def test_reconciliation_does_not_silently_clamp_invalid_manual_plan(self):
        result = self.reconcile(stock_plan=-2, purchase_plan=0)
        self.assertEqual(result["total_source_qty"], -2)
        self.assertEqual(result["shortage_qty"], 10)

    def test_zero_demand_and_empty_sources(self):
        result = self.reconcile(0, 0, 0, 0, 0, 0)
        self.assertEqual(set(result.values()), {0.0})

    def test_nonfinite_or_invalid_quantities_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf, None, "not a number"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    quantity_math.normalize_quantity(value)
                self.assertTrue(quantity_math.manual_split_warnings(value, 0, 0, 0, 0, 0))

    def test_invalid_precision_is_rejected(self):
        for value in (0, -1, math.nan, math.inf, None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "precision"):
                    quantity_math.normalize_quantity(2, precision=value)

    def test_nonzero_quantities_above_epsilon_remain_exact(self):
        result = self.reconcile(
            ordered=0.00005, delivered=0, stock_plan=0.00002,
            purchase_plan=0.00001, precision=1e-8,
        )
        self.assertAlmostEqual(result["pending_qty"], 0.00005)
        self.assertAlmostEqual(result["shortage_qty"], 0.00002)


if __name__ == "__main__":
    unittest.main()
