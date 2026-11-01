import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

from fixtures import workbook, worksheet, cell, N

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preview_parser', ROOT / 'tools/workbook_preview.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ParserTests(unittest.TestCase):
    def read(self, raw=None, **kwargs):
        return p.build_preview(workbook() if raw is None else raw, kwargs.pop('filename', 'book.xlsx'), **kwargs)

    def test_basic_xlsx(self):
        self.assertEqual(self.read()['rows'][0]['cells'][0]['text'], 'Hello')

    def test_bad_dimension_is_ignored(self):
        raw = workbook([('Sheet1', worksheet([(1, cell('A1', 'One')), (2, cell('C2', 'Three'))]), 'visible')])
        result = self.read(raw)
        self.assertEqual((result['total_rows'], result['total_columns']), (2, 3))
        self.assertEqual(result['rows'][1]['cells'][2]['text'], 'Three')

    def test_cached_formula(self):
        result = self.read(workbook([('S', worksheet([(1, cell('A1', None, formula='1+2', cache=3))]), 'visible')]))
        c = result['rows'][0]['cells'][0]
        self.assertEqual(c['text'], '3')
        self.assertTrue(c['formula'])
        self.assertFalse(c['missing_cache'])

    def test_formula_without_cache_is_not_evaluated(self):
        result = self.read(workbook([('S', worksheet([(1, cell('A1', None, formula='HYPERLINK("https://example.invalid", "x")'))]), 'visible')]))
        c = result['rows'][0]['cells'][0]
        self.assertTrue(c['text'].startswith('=HYPERLINK'))
        self.assertTrue(c['missing_cache'])

    def test_number_formats_and_styles(self):
        result = self.read(workbook([('S', worksheet([(1, cell('A1', 1234.5, typ='n', style=1) + cell('B1', 0.25, typ='n', style=2))]), 'visible')]))
        a, b = result['rows'][0]['cells']
        self.assertEqual(a['text'], '1,234.50')
        self.assertEqual(b['text'], '25.00%')
        self.assertEqual(a['style']['background'], '#ABCDEF')
        self.assertEqual(a['style']['color'], '#123456')
        self.assertTrue(a['style']['bold'])
        self.assertEqual(a['style']['align'], 'right')

    def test_date_iso(self):
        result = self.read(workbook([('S', worksheet([(1, cell('A1', 45292, typ='n', style=3))]), 'visible')]))
        self.assertTrue(result['rows'][0]['cells'][0]['text'].startswith('2024-01-01'))

    def test_unicode_html_plain_text(self):
        text = '<img src=x onerror=alert(1)> العربية'
        result = self.read(workbook([('S', worksheet([(1, cell('A1', text))]), 'visible')]))
        self.assertEqual(result['rows'][0]['cells'][0]['text'], text)
        self.assertNotIn('html', result['rows'][0]['cells'][0])

    def test_sheet_selection(self):
        result = self.read(workbook([('One', worksheet([(1, cell('A1', '1'))]), 'visible'),
                                     ('Two', worksheet([(1, cell('A1', '2'))]), 'visible')]), sheet_index=1)
        self.assertEqual(result['sheet_name'], 'Two')
        self.assertEqual(result['rows'][0]['cells'][0]['text'], '2')

    def test_hidden_sheets_not_offered(self):
        raw = workbook([('One', worksheet([(1, cell('A1', 'Visible'))]), 'visible'),
                        ('Secret', worksheet([(1, cell('A1', 'Hidden'))]), 'hidden')])
        result = self.read(raw)
        self.assertEqual(len(result['sheets']), 1)
        with self.assertRaises(p.PreviewError): self.read(raw, sheet_index=1)

    def test_hidden_rows_and_columns(self):
        xml = worksheet([(1, cell('A1', 'Show') + cell('B1', 'Hide')), (2, cell('A2', 'Hide'))],
                        prefix='<cols><col min="2" max="2" hidden="1"/></cols>')
        xml = xml.replace('<row r="2">', '<row r="2" hidden="1">')
        result = self.read(workbook([('S', xml, 'visible')]))
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(len(result['columns']), 1)

    def test_merges(self):
        result = self.read(workbook([('S', worksheet([(1, cell('A1', 'Merged') + cell('B1', '')), (2, cell('B2', ''))],
                         extra='<mergeCells count="1"><mergeCell ref="A1:B2"/></mergeCells>'), 'visible')]))
        self.assertEqual(result['rows'][0]['cells'][0]['colspan'], 2)
        self.assertEqual(result['rows'][0]['cells'][0]['rowspan'], 2)
        self.assertTrue(result['rows'][1]['cells'][1]['hidden'])

    def test_paging(self):
        raw = workbook([('S', worksheet([(i, cell(f'A{i}', str(i))) for i in range(1, 202)]), 'visible')])
        result = self.read(raw, offset=100)
        self.assertEqual(len(result['rows']), 100)
        self.assertEqual(result['rows'][0]['number'], 101)
        self.assertTrue(result['has_previous']); self.assertTrue(result['has_next'])
        last = self.read(raw, offset=200)
        self.assertEqual(len(last['rows']), 1)
        self.assertFalse(last['has_next'])

    def test_truncation_not_silent(self):
        raw = workbook([('S', worksheet([(1, cell('A1', 'a') + cell('CW1', 'outside')), (5001, cell('A5001', 'outside'))]), 'visible')])
        result = self.read(raw)
        self.assertEqual(result['preview_rows'], 5000)
        self.assertEqual(result['preview_columns'], 100)
        self.assertTrue(any('limited' in w for w in result['warnings']))

    def test_long_cell_text(self):
        result = self.read(workbook([('S', worksheet([(1, cell('A1', 'a' * 2500))]), 'visible')]))
        self.assertEqual(len(result['rows'][0]['cells'][0]['text']), p.MAX_CELL_TEXT)
        self.assertTrue(any('shortened' in w for w in result['warnings']))

    def test_empty_sheet(self):
        self.assertFalse(self.read(workbook([('Empty', worksheet([]), 'visible')]))['rows'])

    def test_shared_strings(self):
        raw = workbook([('S', worksheet([(1, cell('A1', 0, typ='s'))]), 'visible')],
                       extras={'xl/sharedStrings.xml': f'<sst xmlns="{N}" count="1" uniqueCount="1"><si><t>Shared</t></si></sst>'})
        self.assertEqual(self.read(raw)['rows'][0]['cells'][0]['text'], 'Shared')

    def test_xlsm_accepted_without_executing_vba(self):
        result = self.read(workbook(extras={'xl/vbaProject.bin': b'non-executable fixture'}), filename='MACROS.XLSM')
        self.assertEqual(result['rows'][0]['cells'][0]['text'], 'Hello')

    def test_csv_utf8(self):
        result = self.read('Code,Name\nSO223,العربية\n'.encode(), filename='test.csv')
        self.assertEqual(result['rows'][1]['cells'][1]['text'], 'العربية')

    def test_csv_utf16(self):
        result = self.read('Code;Name\nSO223;Test\n'.encode('utf-16'), filename='test.csv')
        self.assertEqual(result['rows'][1]['cells'][0]['text'], 'SO223')

    def test_csv_formula_text_leading_zeros(self):
        result = self.read(b'Code,Formula\n00012,=1+2\n', filename='test.csv')
        self.assertEqual(result['rows'][1]['cells'][0]['text'], '00012')
        self.assertEqual(result['rows'][1]['cells'][1]['text'], '=1+2')

    def test_csv_quoted_multiline(self):
        result = self.read(b'Name,Note\nItem,"line one\nline two"\n', filename='test.csv')
        self.assertEqual(result['rows'][1]['cells'][1]['text'], 'line one\nline two')

    def test_csv_many_rows_bounded(self):
        result = self.read(('x\n' * 5500).encode(), filename='test.csv', offset=4900)
        self.assertEqual(result['preview_rows'], 5000)
        self.assertFalse(result['has_next'])

    def test_json_serializable(self):
        json.dumps(self.read())

    def test_invalid_inputs(self):
        cases = [(b'', 'a.xlsx', {}), (workbook(), 'a.xls', {}), (b'notzip', 'a.xlsx', {}),
                 (workbook(), 'a.xlsx', {'offset': -1}), (workbook(), 'a.xlsx', {'offset': True}),
                 (workbook(), 'a.xlsx', {'offset': 50}), (workbook(), 'a.xlsx', {'offset': 5000}),
                 (workbook(), 'a.xlsx', {'sheet_index': '0'}), (workbook(), 'a.xlsx', {'sheet_index': True}),
                 (b'a,b\n1,2', 'a.csv', {'sheet_index': 1}), (b'\xffnotutf8', 'a.csv', {}),
                 (b'a\x00b', 'a.csv', {})]
        for raw, name, args in cases:
            with self.subTest(name=name, args=args):
                with self.assertRaises(p.PreviewError): self.read(raw, filename=name, **args)

    def test_size_limit(self):
        with patch.object(p, 'MAX_FILE_BYTES', 3):
            with self.assertRaises(p.PreviewError): self.read(b'1234', filename='a.csv')

    def test_dtd_rejected(self):
        xml = '<?xml version="1.0"?><!DOCTYPE worksheet [<!ENTITY x "boom">]><worksheet xmlns="' + N + '">&x;</worksheet>'
        with self.assertRaises(p.PreviewError):
            self.read(workbook([('S', xml, 'visible')]))

    def test_traversal_rejected(self):
        with self.assertRaises(p.PreviewError): self.read(workbook(extras={'../outside.xml': '<x/>'}))

    def test_expanded_size_limit(self):
        with patch.object(p, 'MAX_UNCOMPRESSED_BYTES', 10):
            with self.assertRaises(p.PreviewError): self.read()

    def test_archive_count_limit(self):
        with patch.object(p, 'MAX_ARCHIVE_ENTRIES', 2):
            with self.assertRaises(p.PreviewError): self.read()

    def test_xml_node_limit(self):
        with patch.object(p, 'MAX_XML_NODES', 2):
            with self.assertRaises(p.PreviewError): self.read()

    def test_time_budget(self):
        with patch.object(p, 'MAX_PARSE_SECONDS', -1):
            with self.assertRaises(p.PreviewError): self.read()

    def test_out_of_range_page(self):
        with self.assertRaises(p.PreviewError): self.read(offset=100)

    def test_date_boolean_numeric_helpers(self):
        self.assertEqual(p._display(True), 'TRUE')
        self.assertEqual(p._display(dt.date(2026, 11, 1)), '2026-11-01')
        self.assertEqual(p._display(12, '00000'), '00012')
        self.assertEqual(p._display(12.3, 'not-a-format'), '12.3')

    def test_duplicate_paths_rejected(self):
        data = io.BytesIO(workbook())
        with zipfile.ZipFile(data, 'a') as z:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                z.writestr('xl/workbook.xml', '<x/>')
        with self.assertRaises(p.PreviewError): self.read(data.getvalue())


if __name__ == '__main__':
    unittest.main(verbosity=2)
