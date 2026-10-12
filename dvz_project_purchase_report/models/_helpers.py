"""Shared helper: how much of one line belongs to one analytic account."""


def project_share_percent(analytic_id, distribution):
    """Sum of the percentages a line's analytic distribution gives to one account.

    Distribution keys are '3476' or '3476,9912' (one account per plan, comma
    separated), and the value is the percentage. Returns 0.0 if the account
    is not in the distribution.
    """
    if not analytic_id:
        return 0.0
    total = 0.0
    for key, percent in (distribution or {}).items():
        if str(analytic_id) in [part.strip() for part in str(key).split(',')]:
            total += float(percent)
    return total
