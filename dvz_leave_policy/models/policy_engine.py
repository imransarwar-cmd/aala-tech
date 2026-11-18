"""Decimal calculations for the source policy's annual calendar-year grant."""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP


class PolicyCalculationError(ValueError):
    pass


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise PolicyCalculationError("A valid date is required.") from None


def decimal_value(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise PolicyCalculationError("A finite numeric value is required.") from None
    if not result.is_finite():
        raise PolicyCalculationError("A finite numeric value is required.")
    return result


def year_period(on_date):
    on_date = as_date(on_date)
    return date(on_date.year, 1, 1), date(on_date.year, 12, 31)


def rounded_days(value, step=0, method="down"):
    number, increment = decimal_value(value), decimal_value(step)
    if number < 0 or increment < 0:
        raise PolicyCalculationError("Entitlements and rounding increments cannot be negative.")
    modes = {"down": ROUND_FLOOR, "nearest": ROUND_HALF_UP, "up": ROUND_CEILING}
    if method not in modes:
        raise PolicyCalculationError("Unknown rounding method.")
    if increment == 0:
        return number
    return (number / increment).to_integral_value(rounding=modes[method]) * increment


def eligibility(settings, employee, on_date):
    """Require permanent status and an explicitly verified eligibility date.

    The source does not specify a probation duration. Missing dates never
    become confirmation through an assumed number of months.
    """
    on_date = as_date(on_date)
    if not employee.get("joining_date"):
        return {"eligible": False, "joining_date": None, "first_paid_date": None,
                "reason": "Set the employee's verified joining date."}
    joined = as_date(employee["joining_date"])
    first = as_date(employee["first_paid_date"]) if employee.get("first_paid_date") else None
    probation_end = as_date(employee["probation_end_date"]) if employee.get("probation_end_date") else None
    if first and first < joined or probation_end and probation_end < joined:
        raise PolicyCalculationError("Eligibility and probation dates cannot precede joining.")
    if first is None and probation_end:
        first = probation_end + timedelta(days=int(settings.get("probation_end_inclusive", True)))
    if employee.get("status", "unknown") != "permanent":
        return {"eligible": False, "joining_date": joined, "first_paid_date": first,
                "reason": "Confirm permanent employment status before paid leave is available; probation leave is unpaid."}
    if not first:
        return {"eligible": False, "joining_date": joined, "first_paid_date": None,
                "reason": "Set the first paid eligibility date or a verified probation end date."}
    allowed = on_date >= first
    return {"eligible": allowed, "joining_date": joined, "first_paid_date": first,
            "reason": "Eligible for paid leave." if allowed else "Paid eligibility starts on %s." % first.isoformat()}


def entitlement_days(annual_days, period_start, period_end, joining_date, first_paid_date,
                     basis="joining", rounding_step=0, rounding_method="down"):
    """Prorate the annual working-day allowance by actual calendar days.

    Joining-date proration is the source preset. Eligibility-date proration is
    an explicit editable interpretation; it never makes probation leave paid.
    Rounding is applied once to the annual grant and capped at the allowance.
    """
    annual = decimal_value(annual_days)
    if annual < 0:
        raise PolicyCalculationError("Annual entitlement cannot be negative.")
    start, end = as_date(period_start), as_date(period_end)
    joined, first = as_date(joining_date), as_date(first_paid_date)
    if (start, end) != year_period(start) or first < joined:
        raise PolicyCalculationError("Use a complete calendar year and valid eligibility dates.")
    if basis not in ("joining", "eligibility"):
        raise PolicyCalculationError("Unknown proration basis.")
    begin = max(start, joined if basis == "joining" else first)
    if first > end or begin > end:
        return Decimal(0)
    raw = annual * Decimal((end - begin).days + 1) / Decimal((end - start).days + 1)
    return min(annual, rounded_days(raw, rounding_step, rounding_method))

