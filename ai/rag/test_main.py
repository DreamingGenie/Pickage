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
from ai.rag.readme_source import ReadmeSourceNotFoundError
from ai.rag.types import ComparisonResult, FeatureResult, FeatureRow, PackageSource


def _fake_compare_ok(packages):
    return ComparisonResult(
        data_status="COMPLETE",
        packages=packages,
        features=[
            FeatureRow(
                feature_label="구조화 JSON",
                results=[
                    FeatureResult(
                        package=packages[0].name,
                        version=packages[0].version,
                        verdict="SUPPORTED",
                        evidence_ids=["foo@1.0.0#0"],
                        grounded_in="EVIDENCE",
                        note="지원합니다.",
                    )
                ],
            )
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
        self.assertEqual(body["features"][0]["featureLabel"], "구조화 JSON")
        self.assertEqual(body["features"][0]["results"][0]["verdict"], "SUPPORTED")

    def test_verification_failure_returns_502_with_violations(self):
        def fake_compare_fail(packages):
            raise VerificationFailedError(["evidenceId not in pool"])

        client = TestClient(create_app(compare_fn=fake_compare_fail))

        response = client.post(
            "/compare",
            json={"packages": [{"package": "foo", "version": "1.0.0"}]},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["violations"], ["evidenceId not in pool"])



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


if __name__ == "__main__":
    unittest.main()
