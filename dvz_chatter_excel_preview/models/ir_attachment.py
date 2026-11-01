import logging

from odoo import _, models
from odoo.exceptions import AccessError, MissingError, UserError

from ..tools.workbook_preview import MAX_FILE_BYTES, PreviewError, build_preview

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def dvz_excel_preview(self, sheet_index=0, offset=0):
        """Read one bounded worksheet page using the caller's normal rights.

        This RPC never accepts a token, filename, path, model, domain or raw bytes
        supplied by a client. No sudo, writes, conversion attachments or public
        controllers are used.
        """
        self.ensure_one()
        if not self.env.user._is_internal():
            raise AccessError(_("Excel previews are available to internal users only."))
        self.check_access("read")
        if not self.exists():
            raise MissingError(_("The attachment no longer exists."))
        # Also enforce the parent record, including when an attachment is public.
        # An attachment preview must not weaken project/task assignment rules.
        if self.res_model and self.res_id:
            if self.res_model not in self.env:
                raise AccessError(_("The attachment's parent document is unavailable."))
            parent = self.env[self.res_model].browse(self.res_id)
            parent.check_access("read")
            if not parent.exists():
                raise MissingError(_("The attachment's parent document no longer exists."))
        if self.type != "binary":
            raise UserError(_("Only uploaded files can be previewed. External links are not fetched."))
        if self.file_size > MAX_FILE_BYTES:
            raise UserError(_("This file exceeds the 10 MiB preview limit. Use Download instead."))
        raw = self.with_context(bin_size=False, prefetch_fields=False).raw
        try:
            result = build_preview(raw, self.name or "", sheet_index=sheet_index, offset=offset)
        except PreviewError as exc:
            raise UserError(str(exc)) from None
        except Exception:
            # Never return parser tracebacks or cell contents to the browser.
            _logger.warning("Excel preview failed for attachment id=%s", self.id)
            raise UserError(_(
                "This workbook could not be previewed. It may be damaged, encrypted, "
                "or contain unsupported features. Download it to open in Excel."
            )) from None
        result["attachment_id"] = self.id
        result["filename"] = self.name
        return result
