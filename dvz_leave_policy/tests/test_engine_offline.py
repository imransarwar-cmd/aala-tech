"""Run without Odoo: python3 -m unittest discover -s tests -p test_engine_offline.py."""
import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location("dvz_policy_engine", Path(__file__).resolve().parents[1] / "models" / "policy_engine.py")
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)


class PolicyEngineTests(unittest.TestCase):
    def person(self, **overrides):
        return {"joining_date": "2025-01-01", "first_paid_date": "2025-04-01", "status": "permanent", **overrides}

    def test_calendar_year_boundaries(self):
        for day in ("2026-01-01", "2026-06-30", "2026-12-31"):
            self.assertEqual(engine.year_period(day), (date(2026, 1, 1), date(2026, 12, 31)))

    def test_annual_quantity_is_configurable(self):
        for days in (0, 24, 30):
            self.assertEqual(engine.entitlement_days(days, "2026-01-01", "2026-12-31",
                "2024-01-01", "2024-04-01"), Decimal(days))

    def test_new_joiner_uses_actual_calendar_days(self):
        result = engine.entitlement_days(24, "2026-01-01", "2026-12-31", "2026-07-01", "2026-10-01")
        self.assertEqual(result, Decimal(24) * Decimal(184) / Decimal(365))

    def test_leap_year_uses_366_day_denominator(self):
        result = engine.entitlement_days(24, "2024-01-01", "2024-12-31", "2024-07-01", "2024-10-01")
        self.assertEqual(result, Decimal(24) * Decimal(184) / Decimal(366))

    def test_proration_basis_is_explicit_and_editable(self):
        args = (24, "2026-01-01", "2026-12-31", "2026-04-01", "2026-07-01")
        joined = engine.entitlement_days(*args, basis="joining")
        eligible = engine.entitlement_days(*args, basis="eligibility")
        self.assertEqual(joined, Decimal(24) * Decimal(275) / Decimal(365))
        self.assertEqual(eligible, Decimal(24) * Decimal(184) / Decimal(365))
        self.assertGreater(joined, eligible)

    def test_rounding_choices_and_annual_cap(self):
        self.assertEqual(engine.rounded_days("1.25", ".5", "down"), Decimal("1.0"))
        self.assertEqual(engine.rounded_days("1.25", ".5", "nearest"), Decimal("1.5"))
        self.assertEqual(engine.rounded_days("1.01", ".5", "up"), Decimal("1.5"))
        self.assertEqual(engine.entitlement_days("23.7", "2026-01-01", "2026-12-31",
            "2024-01-01", "2024-04-01", rounding_step=".5", rounding_method="up"), Decimal("23.7"))

    def test_source_joining_basis_and_half_day_rounding(self):
        self.assertEqual(engine.entitlement_days(24, "2026-01-01", "2026-12-31",
            "2026-04-01", "2026-07-01", rounding_step=".5", rounding_method="down"), Decimal(18))

    def test_only_permanent_status_can_receive_paid_leave(self):
        for status in ("unknown", "temporary", "probation"):
            self.assertFalse(engine.eligibility({}, self.person(status=status), "2026-01-01")["eligible"])
        self.assertTrue(engine.eligibility({}, self.person(), "2026-01-01")["eligible"])

    def test_missing_eligibility_is_never_inferred_from_service(self):
        info = engine.eligibility({}, self.person(first_paid_date=None), "2060-01-01")
        self.assertFalse(info["eligible"])
        self.assertIsNone(info["first_paid_date"])

    def test_missing_joining_date_is_not_eligible(self):
        info = engine.eligibility({}, self.person(joining_date=None), "2026-01-01")
        self.assertFalse(info["eligible"])
        self.assertIsNone(info["joining_date"])

    def test_verified_probation_boundary_is_configurable(self):
        person = self.person(first_paid_date=None, probation_end_date="2025-03-31")
        self.assertFalse(engine.eligibility({"probation_end_inclusive": True}, person, "2025-03-31")["eligible"])
        self.assertTrue(engine.eligibility({"probation_end_inclusive": True}, person, "2025-04-01")["eligible"])
        self.assertTrue(engine.eligibility({"probation_end_inclusive": False}, person, "2025-03-31")["eligible"])

    def test_explicit_first_paid_date_has_priority(self):
        person = self.person(first_paid_date="2025-03-01", probation_end_date="2025-03-31")
        self.assertEqual(engine.eligibility({}, person, "2025-03-01")["first_paid_date"], date(2025, 3, 1))
        self.assertFalse(engine.eligibility({}, person, "2025-02-28")["eligible"])

    def test_eligibility_after_year_end_has_no_grant(self):
        self.assertEqual(engine.entitlement_days(24, "2026-01-01", "2026-12-31",
            "2026-10-01", "2027-01-01"), Decimal(0))

    def test_invalid_quantities_dates_and_noncalendar_period_are_rejected(self):
        for value in ("NaN", "Infinity", -1):
            with self.assertRaises(engine.PolicyCalculationError):
                engine.entitlement_days(value, "2026-01-01", "2026-12-31", "2025-01-01", "2025-04-01")
        with self.assertRaises(engine.PolicyCalculationError):
            engine.entitlement_days(24, "2026-04-01", "2027-03-31", "2025-01-01", "2025-04-01")
        with self.assertRaises(engine.PolicyCalculationError):
            engine.eligibility({}, self.person(first_paid_date="2024-01-01"), "2026-01-01")
        with self.assertRaises(engine.PolicyCalculationError):
            engine.rounded_days(2, -1)


if __name__ == "__main__":
    unittest.main()

