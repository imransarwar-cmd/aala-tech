"""Small, framework-independent quantity calculations for the sales report.

All quantities passed to these helpers must already use the same unit of
measure.  ``precision`` is an absolute comparison tolerance, not a rounding
increment.  Source plans describe intended coverage; source-used values
describe attributed net deliveries.  Neither is inferred from product stock.
"""

import math


def _precision(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Quantity precision must be a positive finite number.") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError("Quantity precision must be a positive finite number.")
    return result


def normalize_quantity(value, precision=1e-6):
    """Convert a finite number to float and normalize negligible zero noise.

    Non-negligible negative values are intentionally preserved.  Validation
    must report invalid manual quantities rather than silently correcting them.
    """
    tolerance = _precision(precision)
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Quantities must be finite numbers.") from exc
    if not math.isfinite(result):
        raise ValueError("Quantities must be finite numbers.")
    return 0.0 if abs(result) <= tolerance else result


def _quantities(ordered, delivered, stock_plan, purchase_plan, stock_used,
                purchase_used, precision):
    return {
        name: normalize_quantity(value, precision)
        for name, value in (
            ("ordered", ordered),
            ("delivered", delivered),
            ("stock_plan", stock_plan),
            ("purchase_plan", purchase_plan),
            ("stock_used", stock_used),
            ("purchase_used", purchase_used),
        )
    }


def reconcile_source_quantities(ordered, delivered, stock_plan, purchase_plan,
                                stock_used, purchase_used, precision=1e-6):
    """Return report balances without validating or changing stored plans.

    Keeping reconciliation separate from validation lets a report expose a
    stale manual allocation after an SO edit, return, or cancellation without
    preventing the record from being read.

    A negative net delivery is preserved: for 8 ordered and -2 delivered the
    pending balance is 10.  It does not authorize negative source usage, and
    ``manual_split_warnings`` flags that situation for review.
    """
    q = _quantities(ordered, delivered, stock_plan, purchase_plan, stock_used,
                    purchase_used, precision)
    total_source = q["stock_plan"] + q["purchase_plan"]
    result = {
        "pending_qty": max(q["ordered"] - q["delivered"], 0.0),
        "overdelivered_qty": max(q["delivered"] - q["ordered"], 0.0),
        "total_source_qty": total_source,
        "shortage_qty": max(q["ordered"] - total_source, 0.0),
        "unclassified_used_qty": max(
            q["delivered"] - q["stock_used"] - q["purchase_used"], 0.0
        ),
    }
    return {
        name: normalize_quantity(value, precision)
        for name, value in result.items()
    }


def manual_split_warnings(ordered, delivered, stock_plan, purchase_plan,
                          stock_used, purchase_used, precision=1e-6):
    """Return current allocation issues without raising for invalid quantities.

    Overdelivery may legitimately require a plan above the original order, so
    planned coverage is capped at ``max(ordered, delivered, 0)``.  Used source
    quantities are capped at net positive delivery and at their own plans.
    """
    try:
        tolerance = _precision(precision)
        q = _quantities(ordered, delivered, stock_plan, purchase_plan, stock_used,
                        purchase_used, tolerance)
    except ValueError as exc:
        return [str(exc)]

    issues = []
    labels = {
        "stock_plan": "Planned stock quantity",
        "purchase_plan": "Planned purchase quantity",
        "stock_used": "Used stock quantity",
        "purchase_used": "Used purchase quantity",
    }
    for name, label in labels.items():
        if q[name] < -tolerance:
            issues.append("%s cannot be negative." % label)

    if q["ordered"] < -tolerance:
        issues.append(
            "Ordered quantity is negative; review source allocation for this line."
        )
    if q["delivered"] < -tolerance:
        issues.append(
            "Net delivered quantity is negative (returns exceed deliveries); "
            "review the delivery history before confirming a manual source split."
        )

    planned_cap = max(q["ordered"], q["delivered"], 0.0)
    if q["stock_plan"] + q["purchase_plan"] - planned_cap > tolerance:
        issues.append(
            "Total planned source quantity exceeds the greater of ordered and "
            "net delivered quantities."
        )

    delivered_cap = max(q["delivered"], 0.0)
    if q["stock_used"] + q["purchase_used"] - delivered_cap > tolerance:
        issues.append("Total used source quantity exceeds net delivered quantity.")

    if q["stock_used"] - q["stock_plan"] > tolerance:
        issues.append("Used stock quantity exceeds planned stock quantity.")
    if q["purchase_used"] - q["purchase_plan"] > tolerance:
        issues.append("Used purchase quantity exceeds planned purchase quantity.")

    return issues


def validate_manual_split(ordered, delivered, stock_plan, purchase_plan,
                          stock_used, purchase_used, precision=1e-6):
    """Raise ``ValueError`` for an invalid manual split; otherwise return None."""
    issues = manual_split_warnings(
        ordered, delivered, stock_plan, purchase_plan, stock_used, purchase_used,
        precision=precision,
    )
    if issues:
        raise ValueError("\n".join(issues))

