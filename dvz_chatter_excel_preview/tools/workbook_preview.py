"""Bounded read-only workbook renderer. No Odoo or network dependencies.

Supported: genuine OOXML .xlsx/.xlsm and UTF-8/UTF-16 CSV. This is a data
preview, not Excel, a formula engine or a pixel-perfect document renderer.
"""
import csv
import datetime as dt
import io
import math
import re
import time
import zipfile
from contextlib import ExitStack
from pathlib import PurePosixPath

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from openpyxl import load_workbook
from openpyxl.styles.colors import COLOR_INDEX
from openpyxl.utils.cell import get_column_letter, range_boundaries

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ENTRY_BYTES = 24 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2000
MAX_XML_NODES = 600000
MAX_SHEETS = 100
MAX_ROWS = 5000
MAX_COLS = 100
PAGE_SIZE = 100
MAX_CELL_TEXT = 2000
MAX_PAGE_TEXT = 500000
MAX_PARSE_SECONDS = 12
SUPPORTED_EXTENSIONS = {"xlsx", "xlsm", "csv"}

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
HEX_COLOR = re.compile(r"^[0-9a-fA-F]{6}$")
CELL_REF = re.compile(r"^([A-Za-z]{1,3})([1-9][0-9]{0,6})$")


class PreviewError(ValueError):
    """Safe, user-facing parsing error."""


def _check_time(deadline):
    if time.monotonic() > deadline:
        raise PreviewError("This workbook is too complex for a quick preview. Use Download instead.")


def _validate_request(raw, filename, sheet_index, offset):
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        raise PreviewError("This attachment is empty or its file contents are unavailable.")
    if len(raw) > MAX_FILE_BYTES:
        raise PreviewError("This file exceeds the 10 MiB preview limit. Use Download instead.")
    if not isinstance(filename, str):
        raise PreviewError("The attachment filename is invalid.")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in SUPPORTED_EXTENSIONS:
        raise PreviewError("Preview supports .xlsx, .xlsm and .csv. Save older .xls files as .xlsx first.")
    if type(sheet_index) is not int or not 0 <= sheet_index < MAX_SHEETS:
        raise PreviewError("The requested worksheet is invalid.")
    if type(offset) is not int or not 0 <= offset < MAX_ROWS or offset % PAGE_SIZE:
        raise PreviewError("The requested worksheet page is invalid.")
    return extension


def _preflight(raw, deadline):
    """Reject risky archives/XML before a workbook library sees the input."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, OSError):
        raise PreviewError("This is not a readable XLSX/XLSM workbook. Password-protected files are not supported.") from None
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise PreviewError("The workbook contains too many embedded files for preview.")
        names, total, nodes = set(), 0, 0
        for info in entries:
            _check_time(deadline)
            path = PurePosixPath(info.filename)
            if info.filename in names or path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                raise PreviewError("The workbook archive contains invalid or duplicate paths.")
            names.add(info.filename)
            if info.flag_bits & 1:
                raise PreviewError("Encrypted workbooks cannot be previewed.")
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise PreviewError("The workbook uses unsupported ZIP compression.")
            total += info.file_size
            if info.file_size > MAX_ENTRY_BYTES or total > MAX_UNCOMPRESSED_BYTES:
                raise PreviewError("The expanded workbook is too large for preview. Use Download instead.")
            if info.file_size > 1024 * 1024 and info.file_size > max(info.compress_size, 1) * 200:
                raise PreviewError("The workbook exceeds the safe preview compression limit.")
        if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(names):
            raise PreviewError("This archive is not a supported Excel workbook.")
        for info in entries:
            if not info.filename.lower().endswith((".xml", ".rels")):
                continue
            with archive.open(info) as stream:
                try:
                    for _, elem in SafeET.iterparse(stream, events=("end",), forbid_dtd=True,
                                                    forbid_entities=True, forbid_external=True):
                        nodes += 1
                        if nodes > MAX_XML_NODES:
                            raise PreviewError("The workbook contains too many XML elements for preview.")
                        if nodes % 1024 == 0:
                            _check_time(deadline)
                        elem.clear()
                except (DefusedXmlException, SafeET.ParseError):
                    raise PreviewError("The workbook contains invalid or unsafe XML and cannot be previewed.") from None
        _check_time(deadline)


def _safe_text(value, budget, warnings):
    text = str(value) if value is not None else ""
    # Remove control codes, but preserve tab, CR and LF. Owl escapes markup later.
    text = "".join(c for c in text if ord(c) >= 32 or c in "\n\t\r")
    allowance = min(MAX_CELL_TEXT, budget[0])
    if len(text) > allowance:
        text = text[:max(0, allowance - 1)] + ("…" if allowance else "")
        warnings.add("Some long cell text was shortened in this preview. The original file is unchanged.")
    budget[0] -= len(text)
    return text


def _rgb(color):
    if color is None:
        return None
    value = None
    if color.type == "rgb":
        value = color.rgb[-6:] if isinstance(color.rgb, str) else None
    elif color.type == "indexed" and isinstance(color.indexed, int) and 0 <= color.indexed < len(COLOR_INDEX):
        value = COLOR_INDEX[color.indexed][-6:]
    # Theme and tint colours intentionally fall back to the normal viewer style.
    return "#" + value.upper() if value and HEX_COLOR.fullmatch(value) else None


def _style(cell):
    style = {}
    font = getattr(cell, "font", None)
    if font:
        if font.bold:
            style["bold"] = True
        if font.italic:
            style["italic"] = True
        if font.underline:
            style["underline"] = True
        color = _rgb(font.color)
        if color:
            style["color"] = color
    fill = getattr(cell, "fill", None)
    if fill and fill.patternType == "solid":
        color = _rgb(fill.fgColor)
        if color:
            style["background"] = color
    alignment = getattr(cell, "alignment", None)
    if alignment:
        if alignment.horizontal in ("left", "right", "center"):
            style["align"] = alignment.horizontal
        if alignment.wrap_text:
            style["wrap"] = True
    return style


def _display(value, number_format="General"):
    """Stable values, ISO dates and a conservative set of number formats.

    Unsupported custom formats fall back to the underlying value rather than
    guessing a currency, scaling, fraction or accounting rule.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return str(value)
    if isinstance(value, (float, int)):
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        fmt = number_format or "General"
        if re.fullmatch(r"0(?:\.0{1,8})?%", fmt):
            places = len(fmt.split(".")[1].rstrip("%")) if "." in fmt else 0
            return f"{value * 100:.{places}f}%"
        if re.fullmatch(r"(?:#,##)?0(?:\.0{1,8})?", fmt):
            places = len(fmt.split(".")[1]) if "." in fmt else 0
            return format(value, f",.{places}f" if "," in fmt else f".{places}f")
        if re.fullmatch(r"0{2,12}", fmt) and float(value).is_integer():
            return f"{int(value):0{len(fmt)}d}"
        return str(value) if isinstance(value, int) else format(value, ".15g")
    return str(value)


def _base_result(sheet_names, index, offset, total_rows, total_columns):
    rows = min(total_rows, MAX_ROWS)
    cols = min(total_columns, MAX_COLS)
    if rows and offset >= rows:
        raise PreviewError("This page is outside the available worksheet rows.")
    return {
        "sheets": [{"index": i, "name": name} for i, name in enumerate(sheet_names)],
        "sheet_index": index,
        "sheet_name": sheet_names[index],
        "offset": offset,
        "page_size": PAGE_SIZE,
        "total_rows": total_rows,
        "total_columns": total_columns,
        "preview_rows": rows,
        "preview_columns": cols,
        "has_previous": offset > 0,
        "has_next": offset + PAGE_SIZE < rows,
        "columns": [{"index": c, "name": get_column_letter(c)} for c in range(1, cols + 1)],
        "rows": [],
        "warnings": [],
        "limits": {"rows": MAX_ROWS, "columns": MAX_COLS, "file_bytes": MAX_FILE_BYTES},
    }


def _sheet_metadata(raw, worksheet_path, deadline):
    """Inspect XML dimensions without trusting its potentially incorrect dimension tag.

    Used-cell bounds, hidden rows/columns and merged cells are collected with
    bounded memory. No row values are kept here.
    """
    max_row = max_col = 0
    hidden_rows, hidden_cols, merges = set(), set(), []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive, archive.open(worksheet_path) as stream:
        for count, (_, elem) in enumerate(SafeET.iterparse(stream, events=("end",),
                                             forbid_dtd=True, forbid_entities=True, forbid_external=True)):
            if count % 1024 == 0:
                _check_time(deadline)
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag == "c":
                address = elem.get("r", "")
                m = CELL_REF.fullmatch(address)
                if not m:
                    raise PreviewError("A cell has an invalid or missing Excel address.")
                row = int(m.group(2))
                col = 0
                for char in m.group(1).upper():
                    col = col * 26 + ord(char) - 64
                if row > 1048576 or col > 16384:
                    raise PreviewError("A cell address is outside Excel's worksheet bounds.")
                max_row, max_col = max(max_row, row), max(max_col, col)
            elif tag == "row" and elem.get("hidden") in ("1", "true"):
                row = int(elem.get("r", 0))
                if 0 < row <= MAX_ROWS:
                    hidden_rows.add(row)
            elif tag == "col" and elem.get("hidden") in ("1", "true"):
                lo = max(1, int(elem.get("min", 1)))
                hi = min(MAX_COLS, int(elem.get("max", 0)))
                hidden_cols.update(range(lo, hi + 1))
            elif tag == "mergeCell":
                if len(merges) >= 10000:
                    raise PreviewError("The worksheet contains too many merged ranges for preview.")
                try:
                    bounds = range_boundaries(elem.get("ref", ""))
                    if any(v is None for v in bounds):
                        raise ValueError
                    merges.append(bounds)
                except ValueError:
                    raise PreviewError("The worksheet contains an invalid merged-cell range.") from None
            elem.clear()
    return max_row, max_col, hidden_rows, hidden_cols, merges


def _apply_merges(result, merges, warnings):
    """Only merge complete visible ranges on this page. Never duplicate values."""
    rows = {row["number"]: row for row in result["rows"]}
    cols = {col["index"] for col in result["columns"]}
    covered = set()
    visited = 0
    for c1, r1, c2, r2 in merges:
        if r1 > r2 or c1 > c2 or not (1 <= c1 <= 16384 and 1 <= r1 <= 1048576):
            continue
        if not rows or r2 < min(rows) or r1 > max(rows) or c1 > result["preview_columns"]:
            continue
        if r2 - r1 >= PAGE_SIZE or c2 - c1 >= MAX_COLS:
            warnings.add("Merged cells crossing pages, hidden cells or preview limits are shown without merging.")
            continue
        if not all(r in rows for r in range(r1, r2 + 1)) or not all(c in cols for c in range(c1, c2 + 1)):
            warnings.add("Merged cells crossing pages, hidden cells or preview limits are shown without merging.")
            continue
        visited += (r2 - r1 + 1) * (c2 - c1 + 1)
        if visited > 100000:
            warnings.add("Some merged ranges were omitted to keep the preview responsive.")
            break
        positions = {(r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)}
        if positions & covered:
            warnings.add("Overlapping merged ranges were omitted from the preview.")
            continue
        covered.update(positions)
        for r in range(r1, r2 + 1):
            for cell in rows[r]["cells"]:
                c = cell["column"]
                if c1 <= c <= c2:
                    if r == r1 and c == c1:
                        cell["rowspan"], cell["colspan"] = r2 - r1 + 1, c2 - c1 + 1
                    else:
                        cell["hidden"] = True


def _xlsx(raw, sheet_index, offset, deadline):
    _preflight(raw, deadline)
    warnings = {"Read-only data preview. Formula results are saved values and may be stale; formulas are not recalculated."}
    with ExitStack() as stack:
        source = load_workbook(io.BytesIO(raw), read_only=True, data_only=False, keep_links=False, keep_vba=False)
        stack.callback(source.close)
        visible = [ws for ws in source.worksheets if ws.sheet_state == "visible"]
        if not visible:
            raise PreviewError("The workbook has no visible worksheets.")
        if len(source.worksheets) > MAX_SHEETS:
            raise PreviewError("This workbook exceeds the 100-worksheet preview limit.")
        if sheet_index >= len(visible):
            raise PreviewError("The requested worksheet is unavailable or hidden.")
        if len(visible) < len(source.worksheets):
            warnings.add("Hidden worksheets are not displayed. Hiding a worksheet is not a security control.")
        ws = visible[sheet_index]
        total_rows, total_cols, hidden_rows, hidden_cols, merges = _sheet_metadata(raw, ws._worksheet_path, deadline)
        result = _base_result([w.title for w in visible], sheet_index, offset, total_rows, total_cols)
        result["columns"] = [c for c in result["columns"] if c["index"] not in hidden_cols]
        if hidden_rows or hidden_cols:
            warnings.add("Hidden rows and columns are omitted from this preview.")
        cache = load_workbook(io.BytesIO(raw), read_only=True, data_only=True, keep_links=False, keep_vba=False)
        stack.callback(cache.close)
        cached_ws = cache[ws.title]
        # Do not trust producer-written dimension fields; restrict explicit iteration.
        ws.reset_dimensions()
        cached_ws.reset_dimensions()
        end = min(offset + PAGE_SIZE, result["preview_rows"])
        budget = [MAX_PAGE_TEXT]
        if end and result["preview_columns"]:
            args = dict(min_row=offset + 1, max_row=end, min_col=1, max_col=result["preview_columns"])
            for rownum, (source_row, cache_row) in enumerate(zip(ws.iter_rows(**args), cached_ws.iter_rows(**args)), offset + 1):
                _check_time(deadline)
                if rownum in hidden_rows:
                    continue
                row = {"number": rownum, "cells": []}
                for colnum, (cell, cached) in enumerate(zip(source_row, cache_row), 1):
                    if colnum in hidden_cols:
                        continue
                    formula = getattr(cell, "data_type", None) == "f"
                    value = cached.value if formula else cell.value
                    missing_cache = formula and value is None
                    if missing_cache:
                        f = cell.value
                        value = f if isinstance(f, str) else "[Formula: no saved result]"
                        warnings.add("Some formulas have no saved result. Their formula text is shown instead; open and save in Excel to refresh cached values.")
                    row["cells"].append({
                        "address": f"{get_column_letter(colnum)}{rownum}",
                        "column": colnum,
                        "text": _safe_text(_display(value, getattr(cell, "number_format", "General")), budget, warnings),
                        "style": _style(cell),
                        "formula": bool(formula), "missing_cache": bool(missing_cache),
                        "rowspan": 1, "colspan": 1, "hidden": False,
                    })
                result["rows"].append(row)
        _apply_merges(result, merges, warnings)
        _finish(result, warnings)
        _check_time(deadline)
        return result


def _csv(raw, sheet_index, offset, deadline):
    if sheet_index:
        raise PreviewError("A CSV file has only one sheet.")
    try:
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        text = raw.decode(encoding)
    except UnicodeError:
        raise PreviewError("CSV preview requires UTF-8 or UTF-16 text. Save the file as CSV UTF-8 in Excel.") from None
    if "\x00" in text:
        raise PreviewError("This attachment is not a supported text CSV file.")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    warnings = {"CSV values are shown as text. No formulas are evaluated."}
    # Never raise csv.field_size_limit globally: it is process-wide in Odoo workers.
    reader = csv.reader(io.StringIO(text, newline=""), dialect=dialect)
    data, total_rows, cols = [], 0, 0
    try:
        for rownum, row in enumerate(reader, 1):
            _check_time(deadline)
            total_rows = rownum
            cols = max(cols, len(row))
            if offset < rownum <= offset + PAGE_SIZE:
                data.append((rownum, row[:MAX_COLS]))
            if rownum > MAX_ROWS:
                warnings.add("CSV contains more than 5,000 rows; only the first 5,000 can be previewed.")
                break
    except csv.Error:
        raise PreviewError("This CSV contains malformed or unusually large fields. Download it to open in Excel.") from None
    result = _base_result(["CSV"], 0, offset, total_rows, cols)
    budget = [MAX_PAGE_TEXT]
    for rownum, values in data:
        cells = []
        for c in range(1, result["preview_columns"] + 1):
            cells.append({"address": f"{get_column_letter(c)}{rownum}", "column": c,
                          "text": _safe_text(values[c - 1] if c <= len(values) else "", budget, warnings),
                          "style": {}, "formula": False, "missing_cache": False,
                          "rowspan": 1, "colspan": 1, "hidden": False})
        result["rows"].append({"number": rownum, "cells": cells})
    _finish(result, warnings)
    return result


def _finish(result, warnings):
    if result["total_rows"] > MAX_ROWS or result["total_columns"] > MAX_COLS:
        warnings.add("Preview is limited to the first 5,000 rows and 100 columns of each sheet. Download the original for all data.")
    result["warnings"] = sorted(warnings)


def build_preview(raw, filename, *, sheet_index=0, offset=0):
    extension = _validate_request(raw, filename, sheet_index, offset)
    deadline = time.monotonic() + MAX_PARSE_SECONDS
    try:
        return _csv(raw, sheet_index, offset, deadline) if extension == "csv" else _xlsx(raw, sheet_index, offset, deadline)
    except PreviewError:
        raise
    except (zipfile.BadZipFile, DefusedXmlException, SafeET.ParseError, ValueError, KeyError, IndexError, OSError):
        raise PreviewError("This workbook is damaged, encrypted or not supported. Download it to open in Excel.") from None
