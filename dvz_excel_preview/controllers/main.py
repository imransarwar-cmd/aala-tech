import base64
import io
import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, MissingError
from werkzeug.exceptions import Forbidden, NotFound, BadRequest

_logger = logging.getLogger(__name__)
MAX_BYTES = 12 * 1024 * 1024
MAX_ROWS = 500
MAX_COLS = 80

class ExcelPreviewController(http.Controller):
    @http.route('/dvz_excel_preview/attachment/<int:attachment_id>', type='json', auth='user', methods=['POST'])
    def preview(self, attachment_id, **kw):
        # Never sudo: use the same read access check as the requesting user.
        attachment = request.env['ir.attachment'].browse(attachment_id)
        try:
            attachment.check_access('read')
            if not attachment.exists():
                raise MissingError('Attachment does not exist')
            name = attachment.name or ''
            if not name.lower().endswith(('.xlsx', '.xls')):
                return {'error': 'Only .xlsx and .xls files are supported.'}
            data = attachment.raw
        except (AccessError, MissingError):
            raise Forbidden('You cannot access this attachment.')
        if not data:
            return {'error': 'The attachment is empty.'}
        if len(data) > MAX_BYTES:
            return {'error': 'File is too large for inline preview (12 MB limit). Please download it.'}
        try:
            if name.lower().endswith('.xlsx'):
                from openpyxl import load_workbook
                book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
                try:
                    sheets = []
                    for sheet in book.worksheets[:30]:
                        rows = []
                        for row in sheet.iter_rows(min_row=1, max_row=min(sheet.max_row or 1, MAX_ROWS), max_col=min(sheet.max_column or 1, MAX_COLS), values_only=True):
                            rows.append([str(v)[:500] if v is not None else '' for v in row])
                        sheets.append({'name': sheet.title, 'rows': rows, 'truncated': (sheet.max_row or 0) > MAX_ROWS or (sheet.max_column or 0) > MAX_COLS})
                finally:
                    book.close()
            else:
                import xlrd
                book = xlrd.open_workbook(file_contents=data)
                sheets = []
                for sheet in book.sheets()[:30]:
                    rows = [[str(sheet.cell_value(r, c))[:500] for c in range(min(sheet.ncols, MAX_COLS))] for r in range(min(sheet.nrows, MAX_ROWS))]
                    sheets.append({'name': sheet.name, 'rows': rows, 'truncated': sheet.nrows > MAX_ROWS or sheet.ncols > MAX_COLS})
            return {'name': name, 'sheets': sheets}
        except Exception:
            _logger.exception('Excel preview parsing failed for attachment %s', attachment_id)
            return {'error': 'Could not read this workbook. Please download the original file.'}
