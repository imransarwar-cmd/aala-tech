"""Tiny OOXML fixtures built from XML, independent of the parser under test."""
import io
import zipfile
from xml.sax.saxutils import escape

N = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def cell(ref, value, *, typ='inlineStr', style=None, formula=None, cache=None):
    attrs = f'r="{ref}"' + (f' s="{style}"' if style is not None else '')
    if formula is not None:
        return f'<c {attrs}><f>{escape(formula)}</f>' + (f'<v>{cache}</v>' if cache is not None else '') + '</c>'
    if typ == 'inlineStr':
        return f'<c {attrs} t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
    return f'<c {attrs} t="{typ}"><v>{escape(str(value))}</v></c>'


def worksheet(rows, *, extra='', prefix='', dimension='A1:A1'):
    body = ''.join(f'<row r="{i}">{content}</row>' for i, content in rows)
    return f'<worksheet xmlns="{N}"><dimension ref="{dimension}"/>{prefix}<sheetData>{body}</sheetData>{extra}</worksheet>'


STYLES = f'''<styleSheet xmlns="{N}">
<numFmts count="0"/>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><i/><color rgb="FF123456"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFABCDEF"/></patternFill></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="4" fontId="1" fillId="2" borderId="0" xfId="0"><alignment horizontal="right" wrapText="1"/></xf>
<xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0"/>
</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''


def workbook(sheets=None, *, extras=None):
    sheets = sheets or [('Sheet1', worksheet([(1, cell('A1', 'Hello'))]), 'visible')]
    content_types = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    for i in range(1, len(sheets) + 1):
        content_types += f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    if extras and 'xl/sharedStrings.xml' in extras:
        content_types += '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
    content_types += '</Types>'
    sheet_xml = ''.join(f'<sheet name="{escape(name)}" sheetId="{i}" state="{state}" r:id="rId{i}"/>' for i, (name, _, state) in enumerate(sheets, 1))
    rels = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    rels += ''.join(f'<Relationship Id="rId{i}" Type="{R}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
    rels += f'<Relationship Id="styles" Type="{R}/styles" Target="styles.xml"/>'
    if extras and 'xl/sharedStrings.xml' in extras:
        rels += f'<Relationship Id="strings" Type="{R}/sharedStrings" Target="sharedStrings.xml"/>'
    rels += '</Relationships>'
    entries = {
        '[Content_Types].xml': content_types,
        '_rels/.rels': f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="workbook" Type="{R}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': f'<workbook xmlns="{N}" xmlns:r="{R}"><sheets>{sheet_xml}</sheets></workbook>',
        'xl/_rels/workbook.xml.rels': rels,
        'xl/styles.xml': STYLES,
    }
    for i, (_, xml, _) in enumerate(sheets, 1):
        entries[f'xl/worksheets/sheet{i}.xml'] = xml
    entries.update(extras or {})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, value in entries.items():
            z.writestr(name, value)
    return buffer.getvalue()
