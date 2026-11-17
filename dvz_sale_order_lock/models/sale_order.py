from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from .policy import (
    CONTROL_FIELDS, LOCK_GROUP, confirmation_mail_cron_scope,
    in_server_scope, is_confirmation_lock, is_mail_metadata_write,
    is_portal_token_write, lock_status, server_scope,
)
from .view_utils import protect_view


class SaleOrder(models.Model):
    _inherit = "sale.order"

    dvz_lock_status = fields.Selection(
        selection=[("open", "Open"), ("closed", "Closed")],
        string="SO Status",
        compute="_compute_dvz_lock_status",
        store=True,
        index=True,
        readonly=True,
        copy=False,
        help="Open = unlocked. Closed = locked. This does not change the sales, delivery or invoice state.",
    )
    dvz_can_manage_lock = fields.Boolean(
        compute="_compute_dvz_lock_permissions", compute_sudo=False,
        string="Can Manage SO Lock",
    )
    dvz_lock_readonly = fields.Boolean(
        compute="_compute_dvz_lock_permissions", compute_sudo=False,
        string="SO Read-only (Closed)",
    )

    @api.depends("locked")
    def _compute_dvz_lock_status(self):
        for order in self:
            order.dvz_lock_status = lock_status(order.locked)

    @api.depends("locked")
    @api.depends_context("uid")
    def _compute_dvz_lock_permissions(self):
        permitted = self._dvz_is_locked_editor()
        for order in self:
            order.dvz_can_manage_lock = permitted
            order.dvz_lock_readonly = bool(order.locked)

    @api.model
    def _dvz_is_locked_editor(self):
        # Kept for compatibility with v1.1. This now authorizes ONLY lock
        # transitions. Neither this group nor sudo bypasses a Closed order.
        return bool(self.env.su or self.env.user.has_group(LOCK_GROUP))

    def _dvz_require_lock_group(self):
        if not self._dvz_is_locked_editor():
            raise AccessError(_(
                "Only users in 'Sales Order Lock: Manage Lock / Reopen Orders' "
                "can close or reopen a sales order. Reopen it before editing."
            ))

    def _dvz_lock_rows(self, operation="write"):
        """Serialize order edits and lock transitions, respecting existing ACLs.

        Check the database, not a possibly stale cached `locked` value. No
        business values are changed with SQL. Normal ORM writes follow later.
        """
        if not self:
            return {}
        self.check_access(operation)
        self.flush_recordset(["locked"])
        self.env.cr.execute(
            "SELECT id, locked FROM sale_order "
            "WHERE id IN %s ORDER BY id FOR UPDATE",
            [tuple(self.ids)],
        )
        result = dict(self.env.cr.fetchall())
        self.invalidate_recordset(["locked"], flush=False)
        return result

    def _dvz_assert_editable(self, operation="write"):
        flags = self._dvz_lock_rows(operation)
        if any(flags.values()):
            self._dvz_raise_closed_error()

    def _dvz_raise_closed_error(self):
        raise AccessError(_(
            "This sales order is Closed (locked). Its fields and order lines "
            "cannot be changed, even by users who manage locks. An authorized "
            "user must first click Reopen / Unlock. Adding products, sections "
            "or notes, changing quantities/prices, and removing lines are "
            "not allowed while the order is Closed."
        ))

    @api.model
    def _dvz_reject_control_values(self, vals):
        if not self.env.su and CONTROL_FIELDS.intersection(vals):
            raise AccessError(_(
                "SO Status and lock-permission fields are calculated by Odoo. "
                "Use the Close / Lock or Reopen / Unlock buttons instead."
            ))

    @api.model_create_multi
    def create(self, vals_list):
        default_locked = self.default_get(["locked"]).get("locked", False)
        for vals in vals_list:
            self._dvz_reject_control_values(vals)
            if vals.get("locked", default_locked):
                self._dvz_require_lock_group()
        return super().create(vals_list)

    def write(self, vals):
        self._dvz_reject_control_values(vals)
        if not vals:
            return super().write(vals)
        flags = self._dvz_lock_rows()
        permitted = self._dvz_is_locked_editor()
        automatic_lock = is_confirmation_lock(vals, self.env.cr, self.ids)
        if automatic_lock and any(order.state != "sale" for order in self):
            automatic_lock = False
        changing_lock = "locked" in vals and any(
            bool(value) != bool(vals["locked"]) for value in flags.values()
        )
        if changing_lock and not (permitted or automatic_lock):
            self._dvz_require_lock_group()
        if any(flags.values()):
            # An authorized user may change the lock alone. A combined
            # {locked: False, order_line: [...]} payload is deliberately
            # rejected: reopening must be a separate operation before edits.
            lock_transition_only = set(vals) == {"locked"} and permitted
            mail_metadata_only = is_mail_metadata_write(vals, self.env.cr, self.ids)
            portal_token_only = is_portal_token_write(vals, self.env.cr, self.ids)
            if not (automatic_lock or lock_transition_only or mail_metadata_only or portal_token_only):
                self._dvz_raise_closed_error()
        return super().write(vals)

    def unlink(self):
        self._dvz_assert_editable(operation="unlink")
        return super().unlink()

    def action_lock(self):
        automatic = (
            in_server_scope("confirm", self.env.cr, self.ids)
            and all(order.state == "sale" for order in self)
        )
        if not automatic:
            self._dvz_require_lock_group()
        return super().action_lock()

    def action_unlock(self):
        self._dvz_require_lock_group()
        return super().action_unlock()

    def action_dvz_close(self):
        self._dvz_require_lock_group()
        if any(order.state != "sale" for order in self):
            raise UserError(_("Only confirmed Sales Orders can be closed using this button."))
        self.action_lock()
        return True

    def action_dvz_open(self):
        self._dvz_require_lock_group()
        self.action_unlock()
        return True

    def action_confirm(self):
        self._dvz_assert_editable()
        # Keep native 'Lock Confirmed Sales' usable by ordinary salespeople.
        # The capability only permits a True lock transition on these orders.
        with server_scope("confirm", self.env.cr, self.ids):
            return super().action_confirm()

    def _send_order_notification_mail(self, *args, **kwargs):
        # Native asynchronous confirmation-mail scheduling is not a user edit.
        with server_scope("confirmation_mail", self.env.cr, self.ids):
            return super()._send_order_notification_mail(*args, **kwargs)

    @api.model
    def _cron_send_pending_emails(self):
        # Preserve native confirmation email cleanup without a sudo edit bypass.
        with confirmation_mail_cron_scope(self.env.cr):
            return super()._cron_send_pending_emails()

    def _portal_ensure_token(self):
        # Preview/share may lazily create a portal token, not edit the order.
        with server_scope("portal_token", self.env.cr, self.ids):
            return super()._portal_ensure_token()

    def action_update_prices(self):
        self._dvz_assert_editable()
        return super().action_update_prices()

    def action_update_taxes(self):
        self._dvz_assert_editable()
        return super().action_update_taxes()

    def action_open_discount_wizard(self):
        self._dvz_assert_editable()
        return super().action_open_discount_wizard()

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type in {"form", "list", "tree"}:
            def relation(model, name):
                field = self.env[model]._fields.get(name)
                return getattr(field, "comodel_name", None)
            protect_view(arch, self._name, relation)
        return arch, view
