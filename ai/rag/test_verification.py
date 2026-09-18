"""verify_verdicts() 유닛테스트 (S15P21A506-180, unittest, stdlib).

실행: 저장소 루트에서
    python -m unittest ai.rag.test_verification -v
"""

from __future__ import annotations

import unittest

from ai.rag.types import ComparisonResult, EvidenceChunk, FeatureResult, FeatureRow
from ai.rag.verification import verify_evidence_ids, verify_verdicts


def _result(*rows: FeatureRow) -> ComparisonResult:
    return ComparisonResult(data_status="COMPLETE", packages=[], features=list(rows))


def _chunk(evidence_id: str, package: str, version: str) -> EvidenceChunk:
    return EvidenceChunk(
        evidence_id=evidence_id,
        snapshot_id="snap-1",
        package=package,
        version=version,
        section="Usage",
        excerpt="지원합니다.",
        confirmed_content="지원합니다.",
    )


class VerifyVerdictsEmptyTests(unittest.TestCase):
    def test_no_features_passes(self):
        result = _result()

        violations = verify_verdicts(result)

        self.assertEqual(violations, [])


class VerifyVerdictsWhitelistTests(unittest.TestCase):
    def test_disallowed_verdict_value_is_a_violation(self):
        row = FeatureRow(
            feature_label="foo",
            results=[
                FeatureResult(
                    package="foo",
                    version="1.0.0",
                    verdict="YES",
                    evidence_ids=["e1"],
                    grounded_in="EVIDENCE",
                    note="지원함",
                )
            ],
        )

        violations = verify_verdicts(_result(row))

        self.assertEqual(len(violations), 1)


class VerifyVerdictsEvidenceRequiredTests(unittest.TestCase):
    def test_confident_verdict_with_evidence_grounding_but_no_evidence_ids_is_a_violation(self):
        row = FeatureRow(
            feature_label="foo",
            results=[
                FeatureResult(
                    package="foo",
                    version="1.0.0",
                    verdict="SUPPORTED",
                    evidence_ids=[],
                    grounded_in="EVIDENCE",
                    note="지원함",
                )
            ],
        )

        violations = verify_verdicts(_result(row))

        self.assertEqual(len(violations), 1)

    def test_unconfirmed_with_no_evidence_ids_is_not_a_violation(self):
        row = FeatureRow(
            feature_label="foo",
            results=[
                FeatureResult(
                    package="foo",
                    version="1.0.0",
                    verdict="UNCONFIRMED",
                    evidence_ids=[],
                    grounded_in="EVIDENCE",
                    note="",
                )
            ],
        )

        violations = verify_verdicts(_result(row))

        self.assertEqual(violations, [])

    def test_supported_with_evidence_ids_passes(self):
        row = FeatureRow(
            feature_label="foo",
            results=[
                FeatureResult(
                    package="foo",
                    version="1.0.0",
                    verdict="SUPPORTED",
                    evidence_ids=["e1"],
                    grounded_in="EVIDENCE",
                    note="지원함",
                )
            ],
        )

        violations = verify_verdicts(_result(row))

        self.assertEqual(violations, [])


class VerifyVerdictsGeneralKnowledgeTests(unittest.TestCase):
    def test_general_knowledge_with_evidence_ids_is_a_violation(self):
        row = FeatureRow(
            feature_label="foo",
            results=[
                FeatureResult(
                    package="foo",
                    version="1.0.0",
                    verdict="SUPPORTED",
                    evidence_ids=["e1"],
                    grounded_in="GENERAL_KNOWLEDGE",
                    note="일반적으로 지원함",
                )
            ],
        )

        violations = verify_verdicts(_result(row))

        self.assertEqual(len(violations), 1)

    def test_general_knowledge_with_no_evidence_ids_passes(self):
        row = FeatureRow(
            feature_label="foo",
            results=[
                FeatureResult(
                    package="foo",
                    version="1.0.0",
                    verdict="SUPPORTED",
                    evidence_ids=[],
                    grounded_in="GENERAL_KNOWLEDGE",
                    note="일반적으로 지원함",
                )
            ],
        )

        violations = verify_verdicts(_result(row))

        self.assertEqual(violations, [])


class VerifyVerdictsGroundedInWhitelistTests(unittest.TestCase):
    def test_disallowed_grounded_in_value_is_a_violation(self):
        row = FeatureRow(
            feature_label="foo",
            results=[
                FeatureResult(
                    package="foo",
                    version="1.0.0",
                    verdict="SUPPORTED",
                    evidence_ids=["e1"],
                    grounded_in="MADE_UP",
                    note="지원함",
                )
            ],
        )

        violations = verify_verdicts(_result(row))

        self.assertEqual(len(violations), 1)


class VerifyEvidenceIdsExistenceTests(unittest.TestCase):
    def test_evidence_id_present_in_pool_and_owned_by_same_package_version_passes(self):
        row = FeatureRow(
            feature_label="foo",
            results=[
                FeatureResult(
                    package="foo",
                    version="1.0.0",
                    verdict="SUPPORTED",
                    evidence_ids=["e1"],
                    grounded_in="EVIDENCE",
                    note="지원함",
                )
            ],
        )
        pool = [_chunk("e1", "foo", "1.0.0")]

        violations = verify_evidence_ids(_result(row), pool)

        self.assertEqual(violations, [])

    def test_evidence_id_not_in_pool_is_a_violation(self):
        row = FeatureRow(
            feature_label="foo",
            results=[
                FeatureResult(
                    package="foo",
                    version="1.0.0",
                    verdict="SUPPORTED",
                    evidence_ids=["made-up-id"],
                    grounded_in="EVIDENCE",
                    note="지원함",
                )
            ],
        )

        violations = verify_evidence_ids(_result(row), [])

        self.assertEqual(len(violations), 1)


class VerifyEvidenceIdsOwnershipTests(unittest.TestCase):
    def test_evidence_id_from_a_different_package_is_a_violation(self):
        row = FeatureRow(
            feature_label="foo",
            results=[
                FeatureResult(
                    package="foo",
                    version="1.0.0",
                    verdict="SUPPORTED",
                    evidence_ids=["e1"],
                    grounded_in="EVIDENCE",
                    note="지원함",
                )
            ],
        )
        pool = [_chunk("e1", "bar", "1.0.0")]  # 다른 패키지 근거를 foo 셀에 인용

        violations = verify_evidence_ids(_result(row), pool)

        self.assertEqual(len(violations), 1)

    def test_evidence_id_from_a_different_version_is_a_violation(self):
        row = FeatureRow(
            feature_label="foo",
            results=[
                FeatureResult(
                    package="foo",
                    version="2.0.0",
                    verdict="SUPPORTED",
                    evidence_ids=["e1"],
                    grounded_in="EVIDENCE",
                    note="지원함",
                )
            ],
        )
        pool = [_chunk("e1", "foo", "1.0.0")]  # 같은 패키지, 다른 버전

        violations = verify_evidence_ids(_result(row), pool)

        self.assertEqual(len(violations), 1)


if __name__ == "__main__":
    unittest.main()
