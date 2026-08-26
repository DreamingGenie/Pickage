from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from collector.config import SourceRegistry
from collector.contracts import AggregateVerdict
from collector.http_client import HttpClient
from collector.service import CollectionService
from collector.storage import MetadataRepository


def _service(root: str) -> CollectionService:
    return CollectionService(
        registry=SourceRegistry(),
        repository=MetadataRepository(root=root),
        http_client=HttpClient(max_retries=0, sleeper=lambda _seconds: None),
        sleeper=lambda _seconds: None,
    )


def _bus_ridership_csv(*, omit_last_bucket: bool = False) -> bytes:
    row = {
        "USE_YM": "202607",
        "RTE_NO": "N37",
        "RTE_NM": "N37번(진관공영차고지~송파공영차고지)",
        "STOPS_ID": "100000001",
        "STOPS_ARS_NO": "01001",
        "SBWY_STNS_NM": "종로2가사거리(00089)",
        "TRFC_MNS_TYPE_CD": "010",
        "TRFC_MNS_TYPE_NM": "서울간선버스",
        "REG_YMD": "20260803",
    }
    for hour in range(24):
        row[f"HR_{hour}_GET_ON_TNOPE"] = str(hour)
        row[f"HR_{hour}_GET_OFF_TNOPE"] = str(hour + 1)
    if omit_last_bucket:
        row.pop("HR_23_GET_OFF_TNOPE")
    headers = list(row)
    body = ",".join(headers) + "\n" + ",".join(row[name] for name in headers) + "\n"
    return body.encode("cp949")


def _csv_row(row: dict[str, str], encoding: str = "utf-8-sig") -> bytes:
    """Build a one-row provider-style CSV while preserving column order."""
    headers = list(row)
    body = ",".join(headers) + "\n" + ",".join(row[name] for name in headers) + "\n"
    return body.encode(encoding)


def _subway_ridership_csv() -> bytes:
    row = {
        "사용월": "202607",
        "호선명": "2호선",
        "지하철역": "강남",
        "작업일자": "20260803",
    }
    for hour in range(24):
        next_hour = (hour + 1) % 24
        for action in ("승차", "하차"):
            row[f"{hour:02}시-{next_hour:02}시 {action}인원"] = str(hour + 1)
    return _csv_row(row, "cp949")


def _subway_congestion_csv() -> bytes:
    row = {
        "구분": "평일",
        "호선": "2호선",
        "역번호": "0222",
        "역명": "강남",
        "상하구분": "내선",
    }
    # The provider contract has 39 half-hour buckets.  Header identity, not
    # column position, is what the production validator checks.
    for index in range(39):
        start = (5 * 60 + 30 + index * 30) % (24 * 60)
        end = (start + 30) % (24 * 60)
        header = f"{start // 60:02}:{start % 60:02}~{end // 60:02}:{end % 60:02}"
        row[header] = "42.5"
    return _csv_row(row)


class AdditionalSourceCollectionTests(unittest.TestCase):
    def test_representative_rows_cover_every_new_file_contract(self):
        cases = {
            "seoul-subway-ridership-monthly": ("ridership.csv", _subway_ridership_csv()),
            "seoul-subway-congestion-quarterly": (
                "congestion.csv",
                _subway_congestion_csv(),
            ),
            "seoul-station-travel-time": (
                "travel-time.csv",
                _csv_row(
                    {
                        "호선": "8",
                        "역명": "암사",
                        "소요시간": "02:30",
                        "역간거리(km)": "1.2",
                        "호선별누계(km)": "17.8",
                    }
                ),
            ),
            "seoul-subway-timetable-file": (
                "timetable.csv",
                _csv_row(
                    {
                        "ROWNUM": "1",
                        "LINE": "02",
                        "SI_ID": "0222",
                        "STATION_NM": "강남",
                        "WEEKTAG": "DAY",
                        "INOUTTAG": "UP",
                        "GUBHANG": "0",
                        "TRAIN_NO": "2011",
                        "STT": "05:30:00",
                        "EDT": "05:31:00",
                    }
                ),
            ),
            "seoul-subway-transfer-file": (
                "transfer.csv",
                _csv_row(
                    {
                        "고유번호": "1",
                        "환승시작역": "을지로3가",
                        "환승시작 코드": "0203",
                        "환승시작 호선": "2호선",
                        "하차 열차 방면": "내선",
                        "환승종료역": "을지로3가",
                        "환승종료역 코드": "0320",
                        "환승종료 호선": "3호선",
                        "환승 열차 방면": "오금",
                        "소요시간": "04:30",
                    },
                    "cp949",
                ),
            ),
        }
        for source_id, (name, body) in cases.items():
            with self.subTest(source_id=source_id), tempfile.TemporaryDirectory() as tmpdir:
                source = Path(tmpdir) / name
                source.write_bytes(body)
                service = _service(str(Path(tmpdir) / "runtime"))
                try:
                    run = service.collect_files(source_id, [source])
                finally:
                    service.close()
                self.assertEqual(run.report.verdict, AggregateVerdict.USABLE)
                self.assertEqual(run.report.metrics["row_count"], 1)

    def test_cp949_bus_ridership_file_passes_wide_schema_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "ridership.csv"
            source.write_bytes(_bus_ridership_csv())
            service = _service(str(Path(tmpdir) / "runtime"))
            try:
                run = service.collect_files(
                    "seoul-bus-ridership-monthly", [source]
                )
            finally:
                service.close()

        self.assertEqual(run.report.verdict, AggregateVerdict.USABLE)
        self.assertEqual(run.report.metrics["row_count"], 1)
        wide = next(
            check for check in run.report.checks if check.code == "DQ-WIDE-SCHEMA"
        )
        self.assertEqual(wide.status.value, "PASS")
        self.assertEqual(wide.metrics["contracts"][0]["minimum_observed"], 48)

    def test_missing_hour_bucket_is_hard_schema_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "ridership.csv"
            source.write_bytes(_bus_ridership_csv(omit_last_bucket=True))
            service = _service(str(Path(tmpdir) / "runtime"))
            try:
                run = service.collect_files(
                    "seoul-bus-ridership-monthly", [source]
                )
            finally:
                service.close()

        self.assertEqual(run.report.verdict, AggregateVerdict.UNUSABLE)
        wide = next(
            check for check in run.report.checks if check.code == "DQ-WIDE-SCHEMA"
        )
        self.assertEqual(wide.status.value, "FAIL")

    def test_file_only_source_rejects_live_collection_before_network(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = _service(tmpdir)
            try:
                with self.assertRaisesRegex(ValueError, "file-only"):
                    service.collect_live("seoul-subway-timetable-file", {})
            finally:
                service.close()

    def test_static_distance_negative_value_is_unusable(self):
        body = (
            "호선,역명,소요시간,역간거리(km),호선별누계(km)\n"
            "1,서울역,02:00,-1.1,1.1\n"
        ).encode("utf-8-sig")
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "distance.csv"
            source.write_bytes(body)
            service = _service(str(Path(tmpdir) / "runtime"))
            try:
                run = service.collect_files("seoul-station-travel-time", [source])
            finally:
                service.close()

        self.assertEqual(run.report.verdict, AggregateVerdict.UNUSABLE)
        domain = next(check for check in run.report.checks if check.code == "DQ-DOMAIN")
        self.assertEqual(domain.status.value, "FAIL")
        self.assertEqual(domain.metrics["invalid_numeric_count"], 1)

    def test_request_time_path_api_contract_can_be_replayed_without_live_quota(self):
        xml = b"""<?xml version='1.0' encoding='UTF-8'?>
        <ServiceResult>
          <msgHeader><headerCd>0</headerCd><headerMsg>OK</headerMsg></msgHeader>
          <msgBody><itemList><distance>14200</distance><time>51</time></itemList></msgBody>
        </ServiceResult>"""
        for source_id in ("seoul-path-subway", "seoul-path-bus", "seoul-path-mixed"):
            with self.subTest(source_id=source_id), tempfile.TemporaryDirectory() as tmpdir:
                source = Path(tmpdir) / "path.xml"
                source.write_bytes(xml)
                service = _service(str(Path(tmpdir) / "runtime"))
                try:
                    run = service.collect_fixture(
                        source_id,
                        source,
                        params={
                            "startX": "126.9780",
                            "startY": "37.5665",
                            "endX": "127.0276",
                            "endY": "37.4979",
                        },
                    )
                finally:
                    service.close()

                self.assertEqual(run.report.verdict, AggregateVerdict.USABLE)
                self.assertEqual(run.report.metrics["row_count"], 1)
                self.assertEqual(run.items[0].batch.business_code, "0")
                self.assertTrue(run.target.startswith("SENSITIVE_TARGET_SHA256:"))
                self.assertEqual(run.params["startX"], "<redacted>")
                self.assertNotIn("126.9780", str(run.to_summary()))

    def test_request_time_location_contract_can_be_replayed(self):
        xml = b"""<?xml version='1.0' encoding='UTF-8'?>
        <ServiceResult>
          <msgHeader><headerCd>0</headerCd><headerMsg>OK</headerMsg></msgHeader>
          <msgBody><itemList><poiId>123</poiId><poiNm>City Hall</poiNm>
          <gpsX>126.9780</gpsX><gpsY>37.5665</gpsY></itemList></msgBody>
        </ServiceResult>"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "location.xml"
            source.write_bytes(xml)
            service = _service(str(Path(tmpdir) / "runtime"))
            try:
                run = service.collect_fixture(
                    "seoul-path-location", source, params={"stSrch": "시청"}
                )
            finally:
                service.close()

        self.assertEqual(run.report.verdict, AggregateVerdict.USABLE)
        self.assertEqual(run.report.metrics["row_count"], 1)
        self.assertEqual(run.params["stSrch"], "<redacted>")

    def test_station_travel_time_filters_use_documented_path_segments(self):
        spec = SourceRegistry().get("seoul-station-travel-time")
        with patch.dict(os.environ, {"SEOUL_OPEN_API_KEY": "secret-value"}, clear=False):
            url, safe_url, safe_params, _ = HttpClient().prepare(
                spec,
                {"SBWY_ROUT_LN": "8", "SBWY_STNS_NM": "암사"},
                allow_insecure_http=True,
            )

        self.assertIn("/StationDstncReqreTimeHm/1/1000/8/%EC%95%94%EC%82%AC/", url)
        self.assertNotIn("SBWY_ROUT_LN=", url)
        self.assertNotIn("secret-value", safe_url)
        self.assertEqual(safe_params["SBWY_STNS_NM"], "암사")


if __name__ == "__main__":
    unittest.main()
