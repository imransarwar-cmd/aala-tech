"""Checks for the compact five-column Excel export."""

from io import BytesIO
from zipfile import ZipFile

from lxml import etree
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from ..report.xlsx_export import build_sale_supply_xlsx


@tagged("post_install", "-at_install")
class TestSaleSupplyXlsx(TransactionCase):
    def _row(self, **changes):
        row = {"order": "SO0001", "product": "Controller", "ordered": 8,
               "delivered": 8, "stock_used": 6}
        row.update(changes)
        return row

    def _open(self, rows):
        return ZipFile(BytesIO(build_sale_supply_xlsx(rows, {"company_name": "Example Company"})))

    def test_exact_five_columns_one_sheet_and_repeated_product_lines(self):
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with self._open([self._row(), self._row(ordered=2, delivered=1, stock_used=1)]) as archive:
            self.assertIsNone(archive.testzip())
            book = etree.fromstring(archive.read("xl/workbook.xml"))
            self.assertEqual(book.xpath("//m:sheet/@name", namespaces=ns), ["Sales Report"])
            strings = etree.fromstring(archive.read("xl/sharedStrings.xml"))
            values = ["".join(item.itertext()) for item in strings]
            sheet = etree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            header = [values[int(cell.find("m:v", ns).text)] for cell in sheet.xpath("//m:row[@r='1']/m:c", namespaces=ns)]
            self.assertEqual(header, ["SO", "Product Name", "Order Qty", "Delivered Qty", "Used from Stock"])
            self.assertEqual(sheet.xpath("//m:dimension/@ref", namespaces=ns), ["A1:E3"])
            for cell, value in (("C2", "8"), ("D2", "8"), ("E2", "6"), ("E3", "1")):
                self.assertEqual(sheet.xpath("string(//m:c[@r='%s']/m:v)" % cell, namespaces=ns), value)

    def test_numeric_zero_fraction_and_formula_like_names(self):
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows = [self._row(order="=SUM(1,1)", product='=HYPERLINK("https://example.invalid","x")',
                          ordered=0.5, delivered=0, stock_used=0)]
        with self._open(rows) as archive:
            sheet = etree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            self.assertFalse(sheet.xpath("//m:f | //m:hyperlinks", namespaces=ns))
            for cell, value in (("C2", "0.5"), ("D2", "0"), ("E2", "0")):
                self.assertEqual(sheet.xpath("string(//m:c[@r='%s']/m:v)" % cell, namespaces=ns), value)
                self.assertNotEqual(sheet.xpath("string(//m:c[@r='%s']/@t)" % cell, namespaces=ns), "s")
            self.assertIn(b"=SUM(1,1)", archive.read("xl/sharedStrings.xml"))

    def test_zero_stock_usage_is_numeric(self):
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with self._open([self._row(stock_used=0)]) as archive:
            sheet = etree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            self.assertEqual(sheet.xpath("string(//m:c[@r='E2']/m:v)", namespaces=ns), "0")
            self.assertNotEqual(sheet.xpath("string(//m:c[@r='E2']/@t)", namespaces=ns), "s")
