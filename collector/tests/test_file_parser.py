from __future__ import annotations

import io
import unittest
import zipfile

from collector.config import SourceSpec
from collector.parser import parse_document, parse_exchange


def _xlsx_fixture() -> bytes:
    files = {
        "xl/workbook.xml": (
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="기본" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>'
        ),
        "xl/sharedStrings.xml": (
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<si><t>노선</t></si><si><t>상태</t></si></sst>'
        ),
        "xl/worksheets/sheet1.xml": (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1">'
            '<c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c>'
            '</row><row r="2"><c r="A2"><v>7211</v></c>'
            '<c r="B2" t="inlineStr"><is><t>운행</t></is></c></row>'
            '</sheetData></worksheet>'
        ),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


class FileParserTests(unittest.TestCase):
    def test_csv_rejects_cells_beyond_declared_header(self):
        spec = SourceSpec(
            "test-csv",
            {
                "response_format": "csv",
                "row_keys": [],
            },
        )

        batch = parse_exchange(spec, b"first,second\n1,2,unexpected\n", "text/csv")

        self.assertEqual(batch.rows, [])
        self.assertIsNotNone(batch.parse_error)
        self.assertIn("line 2", batch.parse_error or "")
        self.assertIn("header=2, row=3", batch.parse_error or "")

    def test_csv_uses_cp949_and_duplicate_header_suffixes(self) -> None:
        body = "노선,승차,승차\n7211,서울역,10\n".encode("cp949")
        spec = SourceSpec(
            "fixture-csv",
            {"response_format": "csv", "file_encodings": ["utf-8-sig", "cp949"]},
        )

        batch = parse_exchange(spec, body, "text/csv")

        self.assertEqual(batch.response_format, "csv")
        self.assertEqual(batch.rows, [{"노선": "7211", "승차": "서울역", "승차_2": "10"}])

    def test_xlsx_reads_shared_inline_numeric_and_selected_sheet(self) -> None:
        spec = SourceSpec(
            "fixture-xlsx",
            {
                "response_format": "xlsx",
                "sheet_names": ["기본"],
                "string_columns": ["노선"],
            },
        )

        batch = parse_exchange(spec, _xlsx_fixture(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        self.assertEqual(batch.response_format, "xlsx")
        self.assertEqual(batch.rows, [{"노선": "7211", "상태": "운행"}])


    def test_xlsx_rejects_malformed_archive(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid XLSX archive"):
            parse_document(b"not a zip archive", "application/zip", "xlsx")
