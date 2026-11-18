"""Compact five-column sales export; access checks run in the wizard."""

from io import BytesIO
from math import ceil

import xlsxwriter


DETAIL_COLUMNS = (
    ("order", "SO", 20, "text"),
    ("product", "Product Name", 55, "text"),
    ("ordered", "Order Qty", 18, "quantity"),
    ("delivered", "Delivered Qty", 18, "quantity"),
    ("stock_used", "Used from Stock", 22, "quantity"),
)


def build_sale_supply_xlsx(rows, metadata):
    """One sheet and one row per product line, without summary totals.

    Used from Stock is always numeric. Unclassified source data is retained
    in the Odoo detailed record rather than exported as a status string.
    User-entered text never becomes a formula.
    """
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {
        "in_memory": True, "strings_to_formulas": False, "strings_to_urls": False,
    })
    workbook.set_properties({
        "title": "Sales Report", "author": metadata.get("company_name", ""),
        "subject": "Sales orders, product quantities and stock used",
    })
    worksheet = workbook.add_worksheet("Sales Report")
    worksheet.hide_gridlines(2)
    worksheet.set_zoom(100)
    header = workbook.add_format({
        "bold": True, "font_size": 11, "font_color": "#FFFFFF",
        "bg_color": "#173A5E", "text_wrap": True, "valign": "vcenter",
    })
    formats = {}
    for parity in (0, 1):
        base = {
            "font_size": 11, "bg_color": "#FFFFFF" if parity == 0 else "#F0F5FA",
            "valign": "vcenter", "bottom": 1, "bottom_color": "#E0E7EF",
        }
        formats[("text", parity)] = workbook.add_format({**base, "text_wrap": True})
        formats[("quantity", parity)] = workbook.add_format({
            **base, "align": "right", "num_format": "#,##0.###;[Red](#,##0.###);0",
        })
        formats[("status", parity)] = workbook.add_format({
            **base, "font_color": "#8A4B08", "text_wrap": True,
        })
    worksheet.set_row(0, 32)
    for column, (_key, title, width, _kind) in enumerate(DETAIL_COLUMNS):
        worksheet.set_column(column, column, width)
        worksheet.write_string(0, column, title, header)
    for row_number, row in enumerate(rows, start=1):
        parity = (row_number - 1) % 2
        product_lines = sum(max(1, ceil(len(part) / 50)) for part in str(row.get("product") or "").split("\n"))
        worksheet.set_row(row_number, min(120, max(28, 15 * product_lines + 8)))
        for column, (key, _title, _width, kind) in enumerate(DETAIL_COLUMNS):
            value = row.get(key)
            if value is None:
                worksheet.write_blank(row_number, column, None, formats[(kind, parity)])
            elif kind == "text":
                worksheet.write_string(row_number, column, str(value)[:32767], formats[(kind, parity)])
            elif isinstance(value, str):
                worksheet.write_string(row_number, column, value[:32767], formats[("status", parity)])
            else:
                worksheet.write_number(row_number, column, float(value), formats[(kind, parity)])
    worksheet.autofilter(0, 0, len(rows), 4)
    worksheet.freeze_panes(1, 2)
    worksheet.repeat_rows(0)
    worksheet.set_landscape()
    worksheet.set_paper(9)
    worksheet.fit_to_pages(1, 0)
    worksheet.set_margins(0.3, 0.3, 0.4, 0.4)
    worksheet.set_footer("&RPage &P of &N")
    worksheet.print_area(0, 0, len(rows), 4)
    workbook.close()
    return output.getvalue()
