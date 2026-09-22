"""verify_result() 유닛테스트 — 공통점·패키지별 차이점 형식 (2026-09-22).

실행: 저장소 루트에서
    python -m unittest ai.rag.test_verification -v
"""

from __future__ import annotations

import unittest

from ai.rag.types import ComparisonResult, PackageNote, PackageRef
from ai.rag.verification import verify_result

_PACKAGES = [PackageRef("foo", "1.0.0"), PackageRef("bar", "2.0.0")]


def _result(common="공통", *notes: PackageNote) -> ComparisonResult:
    return ComparisonResult(data_status="COMPLETE", packages=_PACKAGES, common=common, differences=list(notes))


def _note(package, version, body="차이"):
    return PackageNote(package=package, version=version, body=body)


class VerifyResultTests(unittest.TestCase):
    def test_one_note_per_package_passes(self):
        self.assertEqual(verify_result(_result("공통", _note("foo", "1.0.0"), _note("bar", "2.0.0")), _PACKAGES), [])

    def test_empty_common_is_a_violation(self):
        violations = verify_result(_result("  ", _note("foo", "1.0.0"), _note("bar", "2.0.0")), _PACKAGES)
        self.assertEqual(violations, ["common 이 비어 있음"])

    def test_missing_package_is_a_violation(self):
        violations = verify_result(_result("공통", _note("foo", "1.0.0")), _PACKAGES)
        self.assertEqual(violations, ["bar: 차이점 문단이 없음"])

    def test_unknown_package_is_a_violation(self):
        violations = verify_result(
            _result("공통", _note("foo", "1.0.0"), _note("bar", "2.0.0"), _note("baz", "1.0.0")), _PACKAGES
        )
        self.assertEqual(violations, ["baz@1.0.0: 요청하지 않은 패키지"])

    def test_changed_version_is_a_violation(self):
        violations = verify_result(_result("공통", _note("foo", "9.9.9"), _note("bar", "2.0.0")), _PACKAGES)
        self.assertEqual(violations, ["foo@9.9.9: 요청한 버전은 1.0.0"])

    def test_duplicate_and_empty_notes_are_violations(self):
        violations = verify_result(
            _result("공통", _note("foo", "1.0.0"), _note("foo", "1.0.0", " "), _note("bar", "2.0.0")), _PACKAGES
        )
        self.assertEqual(
            violations, ["foo@1.0.0: 차이점 문단이 두 번 나옴", "foo@1.0.0: 차이점 문단이 비어 있음"]
        )


if __name__ == "__main__":
    unittest.main()
