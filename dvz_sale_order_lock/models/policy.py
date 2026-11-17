"""Small, ORM-independent policy helpers.

Internal capabilities use ContextVar, never a client-supplied context flag.
Their lifetime is limited to a server method and they cannot be granted via
RPC JSON, CSV import, action context, or a URL parameter.
"""
from contextlib import contextmanager
from contextvars import ContextVar

LOCK_GROUP = "dvz_sale_order_lock.group_manage_locked_sale_orders"
CONTROL_FIELDS = frozenset({
    "dvz_lock_status", "dvz_can_manage_lock", "dvz_lock_readonly",
})
_SERVER_SCOPE = ContextVar("dvz_sale_lock_server_scope", default=())
_MAIL_CRON_SCOPE = ContextVar("dvz_sale_lock_mail_cron_scope", default=())


def lock_status(locked):
    return "closed" if locked else "open"


@contextmanager
def server_scope(purpose, cursor, record_ids):
    """Authorize a narrow server operation, not general editing."""
    grant = (purpose, cursor, frozenset(record_ids))
    token = _SERVER_SCOPE.set(_SERVER_SCOPE.get() + (grant,))
    try:
        yield
    finally:
        _SERVER_SCOPE.reset(token)


def in_server_scope(purpose, cursor, record_ids):
    ids = frozenset(record_ids)
    return bool(ids) and any(
        kind == purpose and cr is cursor and ids <= allowed_ids
        for kind, cr, allowed_ids in _SERVER_SCOPE.get()
    )


def is_confirmation_lock(vals, cursor, record_ids):
    return (
        set(vals) == {"locked"}
        and vals["locked"] is True
        and in_server_scope("confirm", cursor, record_ids)
    )


def is_mail_metadata_write(vals, cursor, record_ids):
    return (
        bool(vals)
        and set(vals) <= {"pending_email_template_id"}
        and (
            in_server_scope("confirmation_mail", cursor, record_ids)
            or any(cr is cursor for cr in _MAIL_CRON_SCOPE.get())
        )
    )


@contextmanager
def confirmation_mail_cron_scope(cursor):
    """Native cron may clear ONLY pending_email_template_id after sending.

    This is a Python capability, not a client-controlled Odoo context flag.
    The record-specific confirmation-mail scope does not cover the native
    cron's subsequent cleanup write, hence this separate metadata-only scope.
    """
    token = _MAIL_CRON_SCOPE.set(_MAIL_CRON_SCOPE.get() + (cursor,))
    try:
        yield
    finally:
        _MAIL_CRON_SCOPE.reset(token)


def is_portal_token_write(vals, cursor, record_ids):
    return (
        set(vals) == {"access_token"}
        and in_server_scope("portal_token", cursor, record_ids)
    )
