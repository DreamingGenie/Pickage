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
from ai.rag.types import ComparisonResult, FeatureResult, FeatureRow


def _fake_compare_ok(packages, variant="A"):
    return ComparisonResult(
        data_status="COMPLETE",
        packages=packages,
        features=[
            FeatureRow(
                feature_label="구조화 JSON",
                results=[
                    FeatureResult(
                        package=packages[0].name,
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
            json={"packages": [{"package": "foo", "version": "1.0.0"}], "variant": "A"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["dataStatus"], "COMPLETE")
        self.assertEqual(body["packages"][0]["package"], "foo")
        self.assertEqual(body["features"][0]["featureLabel"], "구조화 JSON")
        self.assertEqual(body["features"][0]["results"][0]["verdict"], "SUPPORTED")

    def test_verification_failure_returns_502_with_violations(self):
        def fake_compare_fail(packages, variant="A"):
            raise VerificationFailedError(["evidenceId not in pool"])

        client = TestClient(create_app(compare_fn=fake_compare_fail))

        response = client.post(
            "/compare",
            json={"packages": [{"package": "foo", "version": "1.0.0"}]},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["violations"], ["evidenceId not in pool"])


if __name__ == "__main__":
    unittest.main()
