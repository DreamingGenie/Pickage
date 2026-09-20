"""retrieve() 유닛테스트 (S15P21A506-177, unittest, stdlib).

실행: 저장소 루트에서
    python -m unittest ai.rag.test_retrieval -v
"""

from __future__ import annotations

import unittest

from ai.rag.retrieval import retrieve
from ai.rag.types import EvidenceChunk, PackageRef


def _chunk(evidence_id: str, package: str, excerpt: str, verification_level: str = "DISTRIBUTED_ARTIFACT") -> EvidenceChunk:
    return EvidenceChunk(
        evidence_id=evidence_id,
        snapshot_id="snap-1",
        package=package,
        version="1.0.0",
        section="Usage",
        excerpt=excerpt,
        confirmed_content=excerpt,
        verification_level=verification_level,
    )


class RetrieveWithinBudgetTests(unittest.TestCase):
    def test_all_chunks_returned_when_under_budget(self):
        packages = [PackageRef(name="foo", version="1.0.0")]
        chunks = [_chunk("e1", "foo", "a" * 10), _chunk("e2", "foo", "b" * 10)]

        result = retrieve(packages, chunks, max_chars_per_package=1000)

        self.assertEqual([c.evidence_id for c in result], ["e1", "e2"])


class RetrieveOverBudgetTests(unittest.TestCase):
    def test_drops_later_chunks_once_budget_exhausted(self):
        packages = [PackageRef(name="foo", version="1.0.0")]
        chunks = [_chunk("e1", "foo", "a" * 60), _chunk("e2", "foo", "b" * 60), _chunk("e3", "foo", "c" * 60)]

        result = retrieve(packages, chunks, max_chars_per_package=100)

        # e1(60자)로 시작, 남은 예산 40 > 0 이라 e2까지는 더 담고, 그 다음엔 예산 소진.
        self.assertEqual([c.evidence_id for c in result], ["e1", "e2"])


class RetrieveSupplementaryPriorityTests(unittest.TestCase):
    def test_supplementary_pushed_behind_primary_even_if_earlier_in_document(self):
        packages = [PackageRef(name="foo", version="1.0.0")]
        chunks = [
            _chunk("e1", "foo", "a" * 60, verification_level="SUPPLEMENTARY"),
            _chunk("e2", "foo", "b" * 60, verification_level="DISTRIBUTED_ARTIFACT"),
        ]

        result = retrieve(packages, chunks, max_chars_per_package=60)

        # 문서 순서는 e1(보조)->e2(정식)이지만, 정식 근거가 우선이라 e2가 먼저 담기고
        # 예산(60)이 e2(60자)만으로 정확히 소진돼 e1(보조)은 못 들어간다.
        self.assertEqual([c.evidence_id for c in result], ["e2"])


class RetrievePackageScopeTests(unittest.TestCase):
    def test_does_not_mix_other_packages_evidence(self):
        packages = [PackageRef(name="foo", version="1.0.0")]
        chunks = [_chunk("e1", "foo", "hi"), _chunk("e2", "bar", "hi")]

        result = retrieve(packages, chunks, max_chars_per_package=1000)

        self.assertEqual([c.evidence_id for c in result], ["e1"])



class RetrieveMetaEvidenceTests(unittest.TestCase):
    """헤더 근거(#meta-*)가 예산에서 밀려나지 않는다 (S15P21A506-420)."""

    def test_meta_chunks_placed_first_survive_a_tight_budget(self):
        packages = [PackageRef(name="foo", version="1.0.0")]
        chunks = [
            _chunk("foo@1.0.0#meta-entry", "foo", "모듈 형식: type=module"),
            _chunk("foo@1.0.0#0", "foo", "a" * 500),
            _chunk("foo@1.0.0#1", "foo", "b" * 500),
        ]

        result = retrieve(packages, chunks, max_chars_per_package=100)

        self.assertEqual(result[0].evidence_id, "foo@1.0.0#meta-entry")


if __name__ == "__main__":
    unittest.main()
