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
import os
import tempfile
import unittest

import numpy as np

sbp = importlib.import_module("ai.similarity.similarity_batch_pipeline")


class _FakeEmbedder:
    """embed_corpus 테스트용 스텁. 텍스트 길이로 채운 384차원 벡터를 낸다."""

    def __init__(self):
        self.calls = []

    def encode(self, texts, batch_size=32):
        self.calls.append(list(texts))
        return np.array([[float(len(t))] * 384 for t in texts], dtype=np.float32)


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


class BuildText(unittest.TestCase):
    def test_raw_column_used_verbatim_when_given(self):
        row = {"description": "assembled", "body": "  raw value  "}
        self.assertEqual(sbp.build_text(row, "body"), "raw value")

    def test_assembles_description_and_keywords_when_no_raw_column(self):
        row = {"description": "a queue", "keywords": ["queue", "redis"]}
        self.assertEqual(
            sbp.build_text(row, None), "DESCRIPTION: a queue / KEYWORDS: queue, redis"
        )

    def test_keywords_string_is_wrapped(self):
        row = {"description": "d", "keywords": "solo"}
        self.assertEqual(sbp.build_text(row, None), "DESCRIPTION: d / KEYWORDS: solo")

    def test_missing_fields_default_to_empty(self):
        self.assertEqual(sbp.build_text({}, None), "DESCRIPTION:  / KEYWORDS: ")


class Rerank(unittest.TestCase):
    NAMES = ["base", "x", "y", "z", "w"]

    def _hits(self):
        # (base_idx, cand_idx, cos) intentionally out of order
        return [(0, 2, 0.7), (0, 1, 0.9), (0, 3, 0.5), (0, 4, 0.3)]

    def test_score_equals_cosine(self):
        out = sbp.rerank(self._hits(), self.NAMES, k_user=10)
        for row in out:
            self.assertEqual(row["final_score"], row["cos_score"])

    def test_reason_is_semantic_relevance_only(self):
        out = sbp.rerank(self._hits(), self.NAMES, k_user=10)
        self.assertTrue(all(r["ranking_reason"] == ["SEMANTIC_RELEVANCE"] for r in out))

    def test_sorted_by_descending_score_with_ranks_from_one(self):
        out = sbp.rerank(self._hits(), self.NAMES, k_user=10)
        self.assertEqual([r["candidate_package"] for r in out], ["x", "y", "z", "w"])
        self.assertEqual([r["rank"] for r in out], [1, 2, 3, 4])

    def test_user_visible_is_rank_le_3(self):
        out = sbp.rerank(self._hits(), self.NAMES, k_user=10)
        self.assertEqual([r["user_visible"] for r in out], [True, True, True, False])

    def test_default_selected_is_rank_le_2(self):
        out = sbp.rerank(self._hits(), self.NAMES, k_user=10)
        self.assertEqual([r["default_selected"] for r in out], [True, True, False, False])

    def test_k_user_limits_rows_per_base(self):
        out = sbp.rerank(self._hits(), self.NAMES, k_user=2)
        self.assertEqual(len(out), 2)
        self.assertEqual([r["candidate_package"] for r in out], ["x", "y"])

    def test_empty_hits_gives_empty_output(self):
        self.assertEqual(sbp.rerank([], self.NAMES, k_user=10), [])

    def test_multiple_bases_are_grouped_independently(self):
        hits = [(0, 1, 0.9), (2, 3, 0.8), (2, 4, 0.6)]
        out = sbp.rerank(hits, self.NAMES, k_user=10)
        bases = {r["base_package"]: [x["candidate_package"] for x in out if x["base_package"] == r["base_package"]] for r in out}
        self.assertEqual(bases["base"], ["x"])
        self.assertEqual(bases["y"], ["z", "w"])


class TextHash(unittest.TestCase):
    def test_stable_for_same_input(self):
        self.assertEqual(sbp.text_hash("hello"), sbp.text_hash("hello"))

    def test_differs_for_different_input(self):
        self.assertNotEqual(sbp.text_hash("a"), sbp.text_hash("b"))


class LoadState(QuietMixin, unittest.TestCase):
    def test_none_path_returns_empty(self):
        self.assertEqual(sbp.load_state(None), {})

    def test_missing_file_returns_empty(self):
        self.assertEqual(sbp.load_state("no/such/file.parquet"), {})

    def test_reads_name_hash_vector(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.parquet")
            pq.write_table(
                pa.table({"name": ["p"], "text_hash": ["abc"], "vector": [[1.0, 2.0, 3.0]]}),
                path,
            )
            state = sbp.load_state(path)
        self.assertEqual(state["p"]["hash"], "abc")
        np.testing.assert_array_equal(state["p"]["vector"], np.array([1.0, 2.0, 3.0], dtype=np.float32))


class EmbedCorpus(QuietMixin, unittest.TestCase):
    def test_all_rows_embedded_when_state_empty(self):
        rows = [{"name": "a"}, {"name": "b"}]
        emb = _FakeEmbedder()
        sbp.embed_corpus(rows, ["ta", "tbb"], emb, state={}, batch_size=8)
        self.assertEqual(emb.calls, [["ta", "tbb"]])

    def test_row_with_matching_hash_reuses_state_vector(self):
        rows = [{"name": "a"}, {"name": "b"}]
        texts = ["ta", "tbb"]
        cached = np.arange(384, dtype=np.float32)
        state = {"a": {"hash": sbp.text_hash("ta"), "vector": cached}}
        emb = _FakeEmbedder()
        vecs = sbp.embed_corpus(rows, texts, emb, state, batch_size=8)
        self.assertEqual(emb.calls, [["tbb"]])  # only b re-embedded
        np.testing.assert_array_equal(vecs[0], cached)

    def test_row_with_stale_hash_is_reembedded(self):
        rows = [{"name": "a"}]
        state = {"a": {"hash": "stale", "vector": np.zeros(384, dtype=np.float32)}}
        emb = _FakeEmbedder()
        sbp.embed_corpus(rows, ["fresh"], emb, state, batch_size=8)
        self.assertEqual(emb.calls, [["fresh"]])

    def test_writes_text_hash_onto_every_row(self):
        rows = [{"name": "a"}, {"name": "b"}]
        sbp.embed_corpus(rows, ["x", "y"], _FakeEmbedder(), state={}, batch_size=8)
        self.assertEqual(rows[0]["_text_hash"], sbp.text_hash("x"))
        self.assertEqual(rows[1]["_text_hash"], sbp.text_hash("y"))

    def test_output_shape_is_n_by_384(self):
        rows = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        vecs = sbp.embed_corpus(rows, ["a", "b", "c"], _FakeEmbedder(), state={}, batch_size=8)
        self.assertEqual(vecs.shape, (3, 384))


class IsPluginAdapter(unittest.TestCase):
    def test_flags_plugin_names(self):
        for name in (
            "eslint-plugin-react",
            "@babel/plugin-transform-runtime",
            "rollup-plugin-node-resolve",
            "vite-plugin-svgr",
            "@nx/webpack-plugin",
        ):
            with self.subTest(name=name):
                self.assertTrue(sbp.is_plugin_adapter(name, []))

    def test_flags_loader_preset_adapter_config_names(self):
        for name in (
            "css-loader",
            "babel-preset-env",
            "postcss-preset-env",
            "@sveltejs/adapter-node",
            "eslint-config-airbnb",
        ):
            with self.subTest(name=name):
                self.assertTrue(sbp.is_plugin_adapter(name, []))

    def test_does_not_flag_standalone_packages(self):
        for name in ("react", "lodash", "webpack", "eslint", "vite", "plugin", "adapter"):
            with self.subTest(name=name):
                self.assertFalse(sbp.is_plugin_adapter(name, []))

    def test_flags_via_plugin_keyword(self):
        self.assertTrue(sbp.is_plugin_adapter("some-tool", ["logging", "plugin"]))

    def test_keyword_substring_does_not_flag(self):
        self.assertFalse(sbp.is_plugin_adapter("some-tool", ["pluginless", "explaining"]))


class GateAllowsSuccess(unittest.TestCase):
    def test_passed_gate_allows(self):
        self.assertTrue(sbp.gate_allows_success({"status": "PASSED"}, allow_gate_skip=False))

    def test_skipped_allowed_only_with_flag(self):
        self.assertTrue(sbp.gate_allows_success({"status": "SKIPPED"}, allow_gate_skip=True))
        self.assertFalse(sbp.gate_allows_success({"status": "SKIPPED"}, allow_gate_skip=False))

    def test_failed_gate_never_allows(self):
        self.assertFalse(sbp.gate_allows_success({"status": "FAILED"}, allow_gate_skip=True))


if __name__ == "__main__":
    unittest.main()
