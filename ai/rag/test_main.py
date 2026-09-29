"""HTTP 서버(S15P21A506-178, 130이 호출) 유닛테스트.

실제 compare_packages()(아직 175~180 전부 실구현 안 됨)를 부르지 않고 compare_fn을
주입해서 라우팅·직렬화·에러 매핑만 검증한다.

실행: 저장소 루트에서
    python -m unittest ai.rag.test_main -v
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from ai.rag.main import create_app
from ai.rag.pipeline import VerificationFailedError
from ai.rag.readme_source import InvalidPackageRefError, ReadmeSourceNotFoundError
from ai.rag.types import ComparisonResult, Mark, PackageNote, PackageSource


def _fake_compare_ok(packages):
    return ComparisonResult(
        data_status="COMPLETE",
        packages=packages,
        common="설정 파일을 읽어요.",
        differences=[
            PackageNote(package=packages[0].name, version=packages[0].version, body="파일로 설정해요.")
        ],
    )


class ComparePOSTTests(unittest.TestCase):
    def test_returns_serialized_comparison_result(self):
        client = TestClient(create_app(compare_fn=_fake_compare_ok))

        response = client.post(
            "/compare",
            json={"packages": [{"package": "foo", "version": "1.0.0"}]},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["dataStatus"], "COMPLETE")
        self.assertEqual(body["packages"][0]["package"], "foo")
        self.assertEqual(body["common"], "설정 파일을 읽어요.")
        self.assertEqual(
            body["differences"],
            [{"package": "foo", "version": "1.0.0", "body": "파일로 설정해요.", "marks": []}],
        )
        self.assertNotIn("features", body)
        self.assertNotIn("narrative", body)

    def test_verification_failure_returns_502_with_violations(self):
        def fake_compare_fail(packages):
            raise VerificationFailedError(["foo: 차이점 문단이 없음"])

        client = TestClient(create_app(compare_fn=fake_compare_fail))

        response = client.post(
            "/compare",
            json={"packages": [{"package": "foo", "version": "1.0.0"}]},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["violations"], ["foo: 차이점 문단이 없음"])



class DifferenceMarksSerializationTests(unittest.TestCase):
    """차이점 강조 구간 직렬화 (S15P21A506-470)."""

    def test_marks_are_serialized_as_start_end_kind(self):
        def compare_with_marks(packages):
            result = _fake_compare_ok(packages)
            result.differences[0].marks = [
                Mark(start=0, end=3, kind="KEY_SENTENCE"),
                Mark(start=0, end=2, kind="KEY_TERM"),
            ]
            return result

        client = TestClient(create_app(compare_fn=compare_with_marks))

        body = client.post("/compare", json={"packages": [{"package": "foo", "version": "1.0.0"}]}).json()

        self.assertEqual(
            body["differences"][0]["marks"],
            [{"start": 0, "end": 3, "kind": "KEY_SENTENCE"}, {"start": 0, "end": 2, "kind": "KEY_TERM"}],
        )


class SourcesAndNotFoundTests(unittest.TestCase):
    """문헌 상태 전달과 404 (S15P21A506-419)."""

    def test_response_carries_the_document_status_per_package(self):
        def compare_with_sources(packages):
            result = _fake_compare_ok(packages)
            result.sources = [
                PackageSource("foo", "1.0.0", "LIMITED", readme_bytes=917, prose_chars=214),
            ]
            return result

        client = TestClient(create_app(compare_fn=compare_with_sources))

        body = client.post("/compare", json={"packages": [{"package": "foo", "version": "1.0.0"}]}).json()

        self.assertEqual(
            body["sources"],
            [{"package": "foo", "version": "1.0.0", "status": "LIMITED", "readmeBytes": 917, "proseChars": 214}],
        )

    def test_unknown_status_is_null_not_a_guess(self):
        def compare_with_unknown(packages):
            result = _fake_compare_ok(packages)
            result.sources = [PackageSource("foo", "1.0.0")]
            return result

        client = TestClient(create_app(compare_fn=compare_with_unknown))

        source = client.post(
            "/compare", json={"packages": [{"package": "foo", "version": "1.0.0"}]}
        ).json()["sources"][0]

        self.assertIsNone(source["status"])
        self.assertIsNone(source["readmeBytes"])

    def test_existing_fields_are_unchanged_when_no_sources_are_given(self):
        client = TestClient(create_app(compare_fn=_fake_compare_ok))

        body = client.post("/compare", json={"packages": [{"package": "foo", "version": "1.0.0"}]}).json()

        self.assertEqual(body["sources"], [])
        self.assertEqual(body["dataStatus"], "COMPLETE")

    def test_missing_document_is_404_with_a_machine_readable_code_and_no_server_path(self):
        def compare_missing(packages):
            raise ReadmeSourceNotFoundError(
                "/srv/pickage/docs/y/yaml@2.9.1.md", package="yaml", version="2.9.1"
            )

        client = TestClient(create_app(compare_fn=compare_missing))

        response = client.post("/compare", json={"packages": [{"package": "yaml", "version": "2.9.1"}]})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"], {"code": "DOC_NOT_FOUND", "package": "yaml", "version": "2.9.1"}
        )
        self.assertNotIn("/srv/", response.text)

    def test_unsafe_package_reference_is_400_with_a_machine_readable_code(self):
        def compare_unsafe(packages):
            raise InvalidPackageRefError("version", "../../secret")

        client = TestClient(create_app(compare_fn=compare_unsafe))

        response = client.post("/compare", json={"packages": [{"package": "react", "version": "../../secret"}]})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], {"code": "INVALID_PACKAGE_REF", "field": "version"})


if __name__ == "__main__":
    unittest.main()
