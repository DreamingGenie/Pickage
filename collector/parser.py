from __future__ import annotations

import json
import csv
import io
import posixpath
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Iterable

from .config import SourceSpec
from .contracts import ParsedBatch


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_to_value(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        return (element.text or "").strip()
    result: dict[str, Any] = {}
    for child in children:
        key = _strip_namespace(child.tag)
        value = _xml_to_value(child)
        if key in result:
            current = result[key]
            if not isinstance(current, list):
                result[key] = [current]
            result[key].append(value)
        else:
            result[key] = value
    return result


_MAX_FILE_BYTES = 64 * 1024 * 1024
_MAX_XLSX_MEMBERS = 1_000
_MAX_XLSX_UNCOMPRESSED = 256 * 1024 * 1024


def _decode_csv(body: bytes, encodings: Iterable[str] | None) -> str:
    """Decode common Korean public-data encodings without silently losing bytes."""
    if isinstance(encodings, str):
        encodings = (encodings,)
    candidates = list(encodings or ("utf-8-sig", "cp949"))
    for encoding in candidates:
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError) as exc:
            # Try the next declared encoding; the final error is reported below.
            continue
    raise ValueError("CSV decoding failed; tried " + ", ".join(candidates))


def _unique_headers(raw_headers: list[str]) -> list[str]:
    headers: list[str] = []
    counts: dict[str, int] = {}
    for index, value in enumerate(raw_headers, start=1):
        header = value.strip() or f"column_{index}"
        count = counts.get(header, 0) + 1
        counts[header] = count
        headers.append(header if count == 1 else f"{header}_{count}")
    return headers


def _rows_from_csv(body: bytes, encodings: Iterable[str] | None) -> list[dict[str, Any]]:
    """Turn a tabular file into the same row shape used by JSON/XML adapters."""
    text = _decode_csv(body, encodings)
    try:
        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(text), dialect)
        headers: list[str] | None = None
        parsed: list[dict[str, Any]] = []
        for line_number, row in enumerate(reader, start=1):
            if not any(cell.strip() for cell in row):
                continue
            if headers is None:
                headers = _unique_headers(row)
                continue
            # Extra cells are schema drift, not harmless data.  Silently
            # truncating them could hide a newly added provider field or a
            # broken delimiter, so fail this file with an actionable line.
            if len(row) > len(headers):
                raise ValueError(
                    "CSV row has more cells than the header "
                    f"at line {line_number}: header={len(headers)}, row={len(row)}"
                )
            parsed.append(
                {
                    header: (row[index].strip() if index < len(row) else "")
                    for index, header in enumerate(headers)
                }
            )
    except csv.Error as exc:
        raise ValueError(f"CSV parsing failed: {exc}") from exc
    if headers is None:
        raise ValueError("empty CSV response")
    return parsed


def _xlsx_text(element: ET.Element) -> str:
    return "".join((text or "") for text in element.itertext())


def _xlsx_number(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = next((child for child in cell if _strip_namespace(child.tag) == "is"), None)
        return _xlsx_text(inline) if inline is not None else ""
    value = next((child for child in cell if _strip_namespace(child.tag) == "v"), None)
    raw = (value.text or "") if value is not None else ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError) as exc:
            raise ValueError(f"invalid shared-string index: {raw!r}") from exc
    if cell_type == "b":
        return raw == "1"
    return _xlsx_number(raw)


def _safe_zip_members(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > _MAX_XLSX_MEMBERS:
        raise ValueError("XLSX archive contains too many members")
    total = 0
    for info in infos:
        name = info.filename.replace("\\", "/")
        if info.flag_bits & 0x1:
            raise ValueError("encrypted XLSX archives are not supported")
        if name.startswith("/") or ".." in posixpath.normpath(name).split("/"):
            raise ValueError("unsafe XLSX archive member path")
        total += info.file_size
        if info.file_size > _MAX_XLSX_UNCOMPRESSED or total > _MAX_XLSX_UNCOMPRESSED:
            raise ValueError("XLSX archive is too large after decompression")


def _rows_from_xlsx(body: bytes, sheet_names: Iterable[str] | None) -> list[dict[str, Any]]:
    """Read only worksheet XML; pandas/openpyxl are intentionally not required at runtime."""
    if len(body) > _MAX_FILE_BYTES:
        raise ValueError("XLSX response exceeds the safe input size limit")
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError(f"invalid XLSX archive: {exc}") from exc
    with archive:
        _safe_zip_members(archive)
        try:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        except (KeyError, ET.ParseError, zipfile.BadZipFile, OSError, RuntimeError) as exc:
            raise ValueError(f"invalid XLSX workbook metadata: {exc}") from exc
        rel_map = {
            rel.attrib.get("Id"): rel.attrib.get("Target", "")
            for rel in rels
            if rel.attrib.get("Id")
        }
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            try:
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            except (ET.ParseError, zipfile.BadZipFile, OSError, RuntimeError) as exc:
                raise ValueError(f"invalid XLSX shared strings: {exc}") from exc
            shared_strings = [_xlsx_text(item) for item in shared_root if _strip_namespace(item.tag) == "si"]
        if isinstance(sheet_names, str):
            sheet_names = (sheet_names,)
        wanted = {str(name) for name in (sheet_names or ())}
        selected: list[tuple[str, str]] = []
        for sheet in workbook.iter():
            if _strip_namespace(sheet.tag) != "sheet":
                continue
            name = sheet.attrib.get("name", "")
            if wanted and name not in wanted:
                continue
            target = rel_map.get(sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"), "")
            # Relationship targets occur both as `worksheets/...` and
            # `/xl/worksheets/...` in real provider workbooks.
            normalized_target = target.lstrip("/")
            target = (
                posixpath.normpath(normalized_target)
                if normalized_target.startswith("xl/")
                else posixpath.normpath(posixpath.join("xl", normalized_target))
            )
            selected.append((name, target))
        if not selected:
            raise ValueError("configured XLSX sheet was not found" if wanted else "XLSX has no worksheets")
        combined: list[dict[str, Any]] = []
        for _name, target in selected:
            if target not in archive.namelist():
                raise ValueError(f"XLSX worksheet is missing: {target}")
            try:
                root = ET.fromstring(archive.read(target))
            except (ET.ParseError, zipfile.BadZipFile, OSError, RuntimeError) as exc:
                raise ValueError(f"invalid XLSX worksheet {target}: {exc}") from exc
            matrix: list[list[Any]] = []
            for row in root.iter():
                if _strip_namespace(row.tag) != "row":
                    continue
                cells: dict[int, Any] = {}
                for cell in row:
                    if _strip_namespace(cell.tag) != "c":
                        continue
                    ref = cell.attrib.get("r", "")
                    letters = "".join(char for char in ref if char.isalpha())
                    column = 0
                    for char in letters.upper():
                        column = column * 26 + ord(char) - 64
                    if column:
                        cells[column - 1] = _xlsx_cell_value(cell, shared_strings)
                if cells:
                    width = max(cells) + 1
                    matrix.append([cells.get(index, "") for index in range(width)])
            non_empty = [row for row in matrix if any(str(cell).strip() for cell in row)]
            if not non_empty:
                continue
            headers = _unique_headers([str(cell) for cell in non_empty[0]])
            combined.extend(
                {
                    header: (row[index] if index < len(row) else "")
                    for index, header in enumerate(headers)
                }
                for row in non_empty[1:]
            )
        if not combined:
            raise ValueError("XLSX worksheets contain no data rows")
        return combined


def parse_document(
    body: bytes,
    content_type: str | None,
    configured_format: str,
    *,
    file_encodings: Iterable[str] | None = None,
    sheet_names: Iterable[str] | None = None,
) -> tuple[Any, str]:
    if len(body) > _MAX_FILE_BYTES:
        raise ValueError("response exceeds the safe input size limit")
    content_hint = (content_type or "").lower()
    configured = configured_format.lower()
    if configured in {"xlsx", "excel"} or "spreadsheetml" in content_hint or body[:2] == b"PK":
        return _rows_from_xlsx(body, sheet_names), "xlsx"
    text = body.decode("utf-8-sig", errors="replace").strip()
    if not text:
        raise ValueError("empty response body")
    if configured == "csv" or "csv" in content_hint:
        return _rows_from_csv(body, file_encodings), "csv"
    if configured == "json" or "json" in content_hint or text[:1] in ("{", "["):
        return json.loads(text), "json"
    if configured == "xml" or "xml" in content_hint or text.startswith("<"):
        root = ET.fromstring(text)
        return {_strip_namespace(root.tag): _xml_to_value(root)}, "xml"
    if configured == "auto":
        return _rows_from_csv(body, file_encodings), "csv"
    raise ValueError("response format is neither JSON, XML, CSV, nor XLSX")


def _coerce_string_columns(
    rows: list[dict[str, Any]], configured_columns: Iterable[str] | None
) -> None:
    """Preserve identifier semantics when XLSX stores an ID in a numeric cell."""
    wanted = {str(name).casefold() for name in (configured_columns or [])}
    if not wanted:
        return
    for row in rows:
        for key, value in list(row.items()):
            if str(key).casefold() not in wanted or value in (None, ""):
                continue
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            row[key] = str(value)


def _dict_get_ci(value: dict[str, Any], key: str) -> Any:
    if key in value:
        return value[key]
    lowered = key.casefold()
    for candidate, item in value.items():
        if str(candidate).casefold() == lowered:
            return item
    return None


def get_path(document: Any, path: str) -> Any:
    current = document
    for segment in path.split("."):
        if not isinstance(current, dict):
            return None
        current = _dict_get_ci(current, segment)
        if current is None:
            return None
    return current


def first_path(document: Any, paths: Iterable[str]) -> Any:
    for path in paths:
        value = get_path(document, path)
        if value not in (None, ""):
            return value
        value = _find_path_recursive(document, path)
        if value not in (None, ""):
            return value
    return None


def _find_path_recursive(document: Any, path: str) -> Any:
    if isinstance(document, dict):
        value = get_path(document, path)
        if value not in (None, ""):
            return value
        for child in document.values():
            found = _find_path_recursive(child, path)
            if found not in (None, ""):
                return found
    elif isinstance(document, list):
        for child in document:
            found = _find_path_recursive(child, path)
            if found not in (None, ""):
                return found
    return None


def _walk_key_candidates(value: Any, names: set[str]) -> list[Any]:
    candidates: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in names:
                candidates.append(child)
            candidates.extend(_walk_key_candidates(child, names))
    elif isinstance(value, list):
        for child in value:
            candidates.extend(_walk_key_candidates(child, names))
    return candidates


def _rows_from_candidate(candidate: Any) -> list[dict[str, Any]]:
    if isinstance(candidate, list):
        return [row for row in candidate if isinstance(row, dict)]
    if isinstance(candidate, dict):
        # XML frequently wraps repeated rows as {"item": [...]}.
        nested_lists = [value for value in candidate.values() if isinstance(value, list)]
        if nested_lists:
            rows = [row for value in nested_lists for row in value if isinstance(row, dict)]
            if rows:
                return rows
        return [candidate]
    return []


def extract_rows(
    document: Any, row_keys: list[str], row_paths: list[str] | None = None
) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [row for row in document if isinstance(row, dict)]
    for path in row_paths or []:
        rows = _rows_from_candidate(first_path(document, [path]))
        if rows:
            return rows
    names = {name.casefold() for name in row_keys}
    candidates = _walk_key_candidates(document, names)
    row_sets = [_rows_from_candidate(candidate) for candidate in candidates]
    non_empty = [rows for rows in row_sets if rows]
    if not non_empty:
        return []
    return max(non_empty, key=len)


def parse_exchange(spec: SourceSpec, body: bytes, content_type: str | None) -> ParsedBatch:
    try:
        document, response_format = parse_document(
            body,
            content_type,
            spec.get("response_format", "auto"),
            file_encodings=spec.get("file_encodings"),
            sheet_names=spec.get("sheet_names") or spec.get("sheets"),
        )
        business = spec.get("business", {})
        code = first_path(document, business.get("code_paths", []))
        message = first_path(document, business.get("message_paths", []))
        declared = first_path(document, spec.get("declared_count_paths", []))
        try:
            declared_count = int(str(declared)) if declared not in (None, "") else None
        except ValueError:
            declared_count = None
        rows = extract_rows(
            document, spec.get("row_keys", []), spec.get("row_paths", [])
        )
        _coerce_string_columns(rows, spec.get("string_columns"))
        return ParsedBatch(
            source_id=spec.source_id,
            rows=rows,
            business_code=str(code) if code not in (None, "") else None,
            business_message=str(message) if message not in (None, "") else None,
            declared_count=declared_count,
            parse_error=None,
            response_format=response_format,
        )
    except (ValueError, json.JSONDecodeError, ET.ParseError, csv.Error) as exc:
        return ParsedBatch(
            source_id=spec.source_id,
            rows=[],
            business_code=None,
            business_message=None,
            declared_count=None,
            parse_error=f"{type(exc).__name__}: {exc}",
            response_format=None,
        )
