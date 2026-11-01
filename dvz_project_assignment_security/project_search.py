"""Pure project-name search helpers; no Odoo imports or privilege changes.

Only containment operators are enhanced. Exact/equality/membership operators
retain the native meaning by returning None to the caller.
"""
import re


def project_name_tokens(value):
    """Case-insensitive deduplication; split code/word separators, not digits.

    S00716 || ASD-TE-4128-VO -> (S00716, ASD, TE, 4128, VO).
    Alphanumeric fragments are ANDed, so input order does not matter.
    Unicode letters/digits are retained; underscores are separators.
    """
    if not isinstance(value, str):
        return ()
    seen = set()
    tokens = []
    for token in re.findall(r"[^\W_]+", value, flags=re.UNICODE):
        key = token.casefold()
        if key not in seen:
            seen.add(key)
            tokens.append(token)
    return tuple(tokens)


def project_name_domain(operator, value):
    """Return an Odoo prefix domain, or None to use native search semantics.

    Ordinary ilike search is case-insensitive. Every supplied part must be
    present in the *same* project name. Negative containment negates the
    whole conjunction (not each term independently).
    """
    if operator not in ('ilike', 'not ilike'):
        return None
    tokens = project_name_tokens(value)
    if not tokens:
        return None
    clauses = [('name', 'ilike', token) for token in tokens]
    conjunction = ['&'] * (len(clauses) - 1) + clauses
    return ['!'] + conjunction if operator == 'not ilike' else conjunction
