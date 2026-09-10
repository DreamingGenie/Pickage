"""유사도 배치 파이프라인 유닛테스트 (unittest, stdlib).

실행: 저장소 루트에서
    python -m unittest ai.similarity.test_similarity_batch_pipeline -v

무거운 의존성(onnxruntime·transformers·pyarrow)은 각 호출부에서 지연 import 되므로
numpy 만 있으면 순수 로직을 테스트할 수 있다.
"""

import contextlib
import datetime as dt
import importlib
import io
import unittest

import numpy as np

sbp = importlib.import_module("ai.similarity.similarity_batch_pipeline")


class QuietMixin:
    """log() 가 stdout 에 찍는 진행 로그를 삼켜 테스트 출력을 깨끗하게 유지한다."""

    def run(self, result=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return super().run(result)


class ModuleImport(unittest.TestCase):
    def test_imports_with_only_numpy(self):
        """onnxruntime·transformers·pyarrow 없이도 모듈이 import 된다."""
        mod = importlib.import_module("ai.similarity.similarity_batch_pipeline")
        self.assertTrue(hasattr(mod, "qualify"))
        self.assertTrue(hasattr(mod, "rerank"))


class ParseDate(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(sbp._parse_date(None))

    def test_datetime_returns_date(self):
        self.assertEqual(
            sbp._parse_date(dt.datetime(2026, 3, 1, 12, 30)), dt.date(2026, 3, 1)
        )

    def test_date_returned_as_is(self):
        self.assertEqual(sbp._parse_date(dt.date(2026, 3, 1)), dt.date(2026, 3, 1))

    def test_iso_string_prefix_parsed(self):
        self.assertEqual(
            sbp._parse_date("2026-03-01T09:00:00Z"), dt.date(2026, 3, 1)
        )

    def test_unparseable_string_returns_none(self):
        self.assertIsNone(sbp._parse_date("not a date"))


class Qualify(QuietMixin, unittest.TestCase):
    def _row(self, **over):
        row = {
            "name": "pkg",
            "dependent_packages_count": 100,
            "latest_release_published_at": dt.date.today().isoformat(),
            "status": None,
            "is_spam": False,
        }
        row.update(over)
        return row

    def test_keeps_row_passing_all_checks(self):
        kept = sbp.qualify([self._row()], min_dependents=5, max_age_months=12)
        self.assertEqual(len(kept), 1)

    def test_drops_when_dependents_below_min(self):
        kept = sbp.qualify(
            [self._row(dependent_packages_count=4)], min_dependents=5, max_age_months=12
        )
        self.assertEqual(kept, [])

    def test_drops_when_dependents_missing(self):
        kept = sbp.qualify(
            [self._row(dependent_packages_count=None)], min_dependents=5, max_age_months=12
        )
        self.assertEqual(kept, [])

    def test_drops_when_release_older_than_cutoff(self):
        old = (dt.date.today() - dt.timedelta(days=800)).isoformat()
        kept = sbp.qualify(
            [self._row(latest_release_published_at=old)], min_dependents=5, max_age_months=12
        )
        self.assertEqual(kept, [])

    def test_keeps_when_release_date_missing(self):
        kept = sbp.qualify(
            [self._row(latest_release_published_at=None)], min_dependents=5, max_age_months=12
        )
        self.assertEqual(len(kept), 1)

    def test_drops_deprecated_status(self):
        for status in ("deprecated", "removed", "unpublished", "DEPRECATED"):
            with self.subTest(status=status):
                kept = sbp.qualify(
                    [self._row(status=status)], min_dependents=5, max_age_months=12
                )
                self.assertEqual(kept, [])

    def test_drops_spam(self):
        kept = sbp.qualify(
            [self._row(is_spam=True)], min_dependents=5, max_age_months=12
        )
        self.assertEqual(kept, [])

    def test_keeps_unknown_status(self):
        kept = sbp.qualify(
            [self._row(status="active")], min_dependents=5, max_age_months=12
        )
        self.assertEqual(len(kept), 1)


def _unit(rows):
    v = np.array(rows, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


class TopK(QuietMixin, unittest.TestCase):
    # v0≈v1 (cos~0.99), v0⊥v2 (cos 0), v0 opposite v3 (cos -1)
    VECS = _unit([[1.0, 0.0], [0.99, 0.14], [0.0, 1.0], [-1.0, 0.0]])
    NAMES = ["a", "b", "c", "d"]

    def _by_base(self, hits):
        out: dict[int, list] = {}
        for base, cand, cos in hits:
            out.setdefault(base, []).append((cand, cos))
        return out

    def test_excludes_self(self):
        hits = sbp.top_k(self.VECS, self.NAMES, k=2, query_block=10)
        self.assertFalse(any(base == cand for base, cand, _ in hits))

    def test_returns_k_candidates_per_base(self):
        hits = sbp.top_k(self.VECS, self.NAMES, k=2, query_block=10)
        for base, cands in self._by_base(hits).items():
            self.assertEqual(len(cands), 2)

    def test_candidates_sorted_by_descending_cosine(self):
        hits = sbp.top_k(self.VECS, self.NAMES, k=3, query_block=10)
        for base, cands in self._by_base(hits).items():
            cosines = [cos for _, cos in cands]
            self.assertEqual(cosines, sorted(cosines, reverse=True))

    def test_top_candidate_for_a_is_b(self):
        hits = sbp.top_k(self.VECS, self.NAMES, k=1, query_block=10)
        self.assertEqual(self._by_base(hits)[0][0][0], 1)  # base a → cand b

    def test_query_block_smaller_than_n_gives_same_result(self):
        full = sbp.top_k(self.VECS, self.NAMES, k=2, query_block=10)
        blocked = sbp.top_k(self.VECS, self.NAMES, k=2, query_block=2)
        self.assertEqual(sorted(full), sorted(blocked))

    def test_cosine_value_matches_dot_product(self):
        hits = sbp.top_k(self.VECS, self.NAMES, k=1, query_block=10)
        base, cand, cos = next(h for h in hits if h[0] == 0)
        self.assertAlmostEqual(cos, float(self.VECS[0] @ self.VECS[cand]), places=5)


if __name__ == "__main__":
    unittest.main()
