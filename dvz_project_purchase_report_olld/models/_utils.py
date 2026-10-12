"""Small SQL helpers shared by the report views.

The views below read Odoo's own tables directly. A few columns differ a
little between Odoo builds, so each one is checked first and a safe
fallback is used instead of letting the whole module upgrade crash.
"""


def has_column(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(cr.fetchone())


def rate_sql(cr, table, alias):
    """SQL for 'document currency units per 1 company-currency unit'.

    Dividing a document-currency amount by this gives the amount in
    company currency, at the rate stored on the order itself. Falls back
    to 1 (no conversion) if the order table has no currency_rate column.
    """
    if has_column(cr, table, 'currency_rate'):
        return "COALESCE(NULLIF(%s.currency_rate, 0), 1)" % alias
    return "1"


def column_or_null(cr, table, alias, column, sql_type='integer'):
    """'alias.column' if the column exists, else a typed NULL."""
    if has_column(cr, table, column):
        return "%s.%s" % (alias, column)
    return "NULL::%s" % sql_type
