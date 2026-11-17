"""Pure quantity policy. Quantities are in the individual move's UoM.

No stock is changed here. The ORM adapter uses normal Odoo reservation APIs.
"""
from math import isfinite


OPERATOR_GROUP = 'dvz_material_reservation.group_reservation_operator'
# Identity, not a serializable boolean: clients cannot supply this capability.
INTERNAL_TOKEN = object()


def finite_nonnegative(value, label='Quantity'):
    value = float(value)
    if not isfinite(value) or value < 0:
        raise ValueError(f'{label} must be a finite, non-negative number.')
    return value


def effective_target(demand, limited=False, limit=0):
    demand = finite_nonnegative(demand)
    return min(demand, finite_nonnegative(limit)) if limited else demand


def additional_to_reserve(demand, reserved, limited=False, limit=0, force=False):
    """Odoo 19 force_qty means ADDITIONAL quantity, not the new total."""
    reserved = finite_nonnegative(reserved)
    missing = max(effective_target(demand, limited, limit) - reserved, 0.0)
    return min(missing, finite_nonnegative(force)) if force else missing


def release_target(reserved, release, rounding=0.000001):
    reserved = finite_nonnegative(reserved)
    release = finite_nonnegative(release)
    if release <= 0:
        raise ValueError('Enter a quantity greater than zero to release.')
    if release > reserved + rounding / 2:
        raise ValueError('The release quantity exceeds the currently reserved quantity.')
    return max(reserved - release, 0.0)


def split_target(demand, target, split_quantity):
    """Allocate an existing cap to a split/backorder, without copying it twice."""
    demand = finite_nonnegative(demand)
    target = min(finite_nonnegative(target), demand)
    split_quantity = finite_nonnegative(split_quantity)
    return min(split_quantity, max(target - max(demand - split_quantity, 0.0), 0.0))


def quantity_columns(demand, reserved, limited=False, limit=0, finished=False):
    target = 0.0 if finished else effective_target(demand, limited, limit)
    reserved = 0.0 if finished else finite_nonnegative(reserved)
    return {
        'reserved': reserved,
        'target': target,
        'shortage': max(target - reserved, 0.0),
        'on_hold': 0.0 if finished else max(demand - target, 0.0),
    }
