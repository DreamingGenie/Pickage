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


class LoadDependents(QuietMixin, unittest.TestCase):
    """S15P21A506-173: package_dependents 류 parquet(name·kind·dependents) 로더."""

    def test_none_path_returns_empty(self):
        self.assertEqual(sbp.load_dependents(None), {})

    def test_missing_file_returns_empty(self):
        self.assertEqual(sbp.load_dependents("no/such/file.parquet"), {})

    def test_reads_regular_kind_as_sets(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dependents.parquet")
            pq.write_table(
                pa.table({
                    "name": ["webpack", "webpack", "webpack-cli"],
                    "kind": ["regular", "peer", "regular"],
                    "dependents": [["a", "b", "c"], ["x"], ["a", "b"]],
                }),
                path,
            )
            deps = sbp.load_dependents(path)
        self.assertEqual(deps["webpack"], {"a", "b", "c"})
        self.assertEqual(deps["webpack-cli"], {"a", "b"})

    def test_other_kind_can_be_selected(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dependents.parquet")
            pq.write_table(
                pa.table({
                    "name": ["webpack"],
                    "kind": ["peer"],
                    "dependents": [["x", "y"]],
                }),
                path,
            )
            deps = sbp.load_dependents(path, kind="peer")
        self.assertEqual(deps["webpack"], {"x", "y"})


    def _write(self, d):
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = os.path.join(d, "dependents.parquet")
        pq.write_table(
            pa.table({
                "name": ["webpack", "webpack", "webpack-cli", "rollup", "left-pad"],
                "kind": ["regular", "peer", "regular", "regular", "regular"],
                "dependents": [["a", "b", "c"], ["x"], ["a", "b"], ["z"], []],
            }),
            path,
        )
        return path

    def test_names_keeps_only_requested_packages(self):
        """이번 배치 패키지가 아닌 행은 파이썬 객체로 풀기 전에 버린다(메모리)."""
        with tempfile.TemporaryDirectory() as d:
            deps = sbp.load_dependents(self._write(d), names=["webpack", "rollup", "not-in-file"])
        self.assertEqual(set(deps), {"webpack", "rollup"})
        self.assertEqual(deps["webpack"], {"a", "b", "c"})

    def test_names_none_keeps_every_regular_row(self):
        with tempfile.TemporaryDirectory() as d:
            deps = sbp.load_dependents(self._write(d))
        self.assertEqual(set(deps), {"webpack", "webpack-cli", "rollup", "left-pad"})

    def test_names_and_kind_combine(self):
        with tempfile.TemporaryDirectory() as d:
            deps = sbp.load_dependents(self._write(d), kind="peer", names=["webpack", "rollup"])
        self.assertEqual(deps, {"webpack": {"x"}})

    def test_empty_dependents_row_is_kept_as_empty_set(self):
        with tempfile.TemporaryDirectory() as d:
            deps = sbp.load_dependents(self._write(d), names=["left-pad"])
        self.assertEqual(deps, {"left-pad": set()})


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

    def test_mixed_reuse_and_reembed_keep_row_positions(self):
        """재사용·재임베딩이 섞여도 각 벡터가 제 행 위치에 들어간다."""
        rows = [{"name": "a"}, {"name": "b"}, {"name": "c"}, {"name": "d"}]
        texts = ["ta", "tbb", "tccc", "tdddd"]
        cached_a = np.full(384, 7.0, dtype=np.float32)
        cached_c = np.full(384, 9.0, dtype=np.float32)
        state = {
            "a": {"hash": sbp.text_hash("ta"), "vector": cached_a},
            "b": {"hash": "stale", "vector": np.zeros(384, dtype=np.float32)},
            "c": {"hash": sbp.text_hash("tccc"), "vector": cached_c},
        }
        emb = _FakeEmbedder()
        vecs = sbp.embed_corpus(rows, texts, emb, state, batch_size=8)
        self.assertEqual(emb.calls, [["tbb", "tdddd"]])
        np.testing.assert_array_equal(vecs[0], cached_a)
        np.testing.assert_array_equal(vecs[1], np.full(384, 3.0, dtype=np.float32))
        np.testing.assert_array_equal(vecs[2], cached_c)
        np.testing.assert_array_equal(vecs[3], np.full(384, 5.0, dtype=np.float32))

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

    def test_own_plugin_tag_does_not_flag_host(self):
        # '<자기 이름>-plugin' 은 "이 패키지용 플러그인을 만들 때 쓰는 태그" — 이 패키지가 호스트라는 뜻이다.
        self.assertFalse(sbp.is_plugin_adapter("markdown-it", ["markdown", "markdown-it-plugin"]))
        self.assertFalse(sbp.is_plugin_adapter("heroku", ["heroku-cli-plugin"]))
        self.assertFalse(sbp.is_plugin_adapter("vite", ["vite-plugin"]))

    def test_other_packages_plugin_tag_still_flags(self):
        # 태그가 다른 패키지를 가리키면 그 패키지에 얹히는 부속품이다.
        self.assertTrue(sbp.is_plugin_adapter("postcss-nested", ["postcss-plugin"]))
        self.assertTrue(sbp.is_plugin_adapter("autoprefixer", ["postcss-plugin", "plugin"]))

    def test_scoped_name_is_not_exempt_from_own_tag(self):
        # '@unocss/vite' 는 스코프를 벗기면 'vite' 지만 vite 가 아니라 vite 플러그인이다.
        self.assertTrue(sbp.is_plugin_adapter("@unocss/vite", ["vite-plugin"]))
        self.assertTrue(sbp.is_plugin_adapter("@unocss/webpack", ["webpack-plugin"]))

    def test_own_plugin_tag_exemption_keeps_other_keywords_active(self):
        self.assertTrue(sbp.is_plugin_adapter("markdown-it", ["markdown-it-plugin", "plugin"]))


class IsSameFamily(unittest.TestCase):
    def test_flags_submodule_and_repackage(self):
        for a, b in (
            ("d3", "d3-axis"),
            ("lodash", "lodash.pickby"),
            ("lodash", "lodash-es"),
            ("react", "react-dom"),
            ("chalk", "chalk-animation"),
        ):
            with self.subTest(pair=(a, b)):
                self.assertTrue(sbp.is_same_family(a, b))

    def test_flags_same_npm_scope(self):
        self.assertTrue(sbp.is_same_family("@babel/core", "@babel/preset-env"))
        self.assertTrue(sbp.is_same_family("@aws-sdk/client-s3", "@aws-sdk/client-dynamodb"))

    def test_does_not_flag_genuine_alternatives(self):
        for a, b in (
            ("react", "preact"),
            ("express", "fastify"),
            ("vue", "vuex"),
            ("moment", "dayjs"),
        ):
            with self.subTest(pair=(a, b)):
                self.assertFalse(sbp.is_same_family(a, b))

    def test_symmetric(self):
        self.assertEqual(
            sbp.is_same_family("d3", "d3-scale"), sbp.is_same_family("d3-scale", "d3")
        )

    def test_does_not_flag_scoped_vs_unscoped_name_coincidence(self):
        """S15P21A506-334: 스코프를 벗겨낸 뒤 접두어만 비교하면, 서로 무관한
        패키지가 우연히 같은 단어를 이름에 포함할 때 오탐한다."""
        for a, b in (
            ("markdown-it", "@ts-stack/markdown"),
            ("@ts-stack/markdown", "markdown-it"),
        ):
            with self.subTest(pair=(a, b)):
                self.assertFalse(sbp.is_same_family(a, b))

    def test_flags_unscoped_name_matching_scope_org(self):
        """S15P21A506-334 후속: 스코프 없는 이름이 상대방의 스코프(조직명)와
        정확히 같으면, 그 조직이 낸 서브패키지로 본다 — parcel 이 낸
        @parcel/graph 를 parcel 의 "대안"으로 잘못 추천하는 사례(실측)."""
        for a, b in (
            ("parcel", "@parcel/graph"),
            ("@parcel/graph", "parcel"),
            ("vitest", "@vitest/runner"),
            ("rollup", "@rollup/browser"),
        ):
            with self.subTest(pair=(a, b)):
                self.assertTrue(sbp.is_same_family(a, b))

    def test_does_not_flag_unrelated_scope_org(self):
        """스코프(조직명) 자체가 다르면 여전히 무관한 패키지로 남는다 —
        조직명 일치라는 좁은 조건만 잡고, 그 밖의 우연한 접두어 겹침이나
        느슨하게 연관된 리브랜딩(passport vs passport-next)까지 잡지 않는다."""
        for a, b in (
            ("markdown-it", "@ts-stack/markdown"),
            ("terser", "@node-minify/babel-minify"),
            ("passport", "@passport-next/passport"),
        ):
            with self.subTest(pair=(a, b)):
                self.assertFalse(sbp.is_same_family(a, b))

    def test_flags_types_declaration_package(self):
        """@types/X 는 항상 X 의 타입 선언 파일 — DefinitelyTyped 관례상 예외가
        없어 X 자신의 "대안"으로 추천되면 안 된다."""
        for a, b in (
            ("lodash", "@types/lodash"),
            ("@types/lodash", "lodash"),
            ("express", "@types/express"),
        ):
            with self.subTest(pair=(a, b)):
                self.assertTrue(sbp.is_same_family(a, b))

    def test_types_scope_requires_matching_subpath(self):
        """@types/ 규칙은 스코프 뒤 이름이 정확히 같을 때만 — 엉뚱한 패키지의
        타입 선언까지 같은 계열로 잡지 않는다."""
        self.assertFalse(sbp.is_same_family("lodash", "@types/express"))


class IsRepoArchived(unittest.TestCase):
    def test_flags_true(self):
        self.assertTrue(sbp.is_repo_archived(True))

    def test_does_not_flag_false(self):
        self.assertFalse(sbp.is_repo_archived(False))

    def test_does_not_flag_none(self):
        """repo_full_name 이 없어 repo_stat 과 LEFT JOIN 이 안 되면 NULL — 보관 아님으로 취급."""
        self.assertFalse(sbp.is_repo_archived(None))


class IsComplement(unittest.TestCase):
    """S15P21A506-173: dependents(나를 쓰는 패키지) 집합 겹침으로 보완재를 판별.

    비율은 교집합 ÷ 둘 중 더 작은 쪽 크기(containment) — 실측(2026-09-16, 후보 풀
    29,310개 기준 dependents)으로 이 계산이 보완재(webpack↔webpack-cli 0.903,
    express↔body-parser 0.873)와 진짜 대안(webpack↔rollup 0.075)을 뚜렷하게
    갈라놓는 걸 확인함. 큰 쪽 기준으로 나누면(webpack↔webpack-cli 0.237) 신호가
    뭉개져서 이 방식을 쓰지 않는다.
    """

    def test_flags_high_overlap_as_complement(self):
        base = {f"user{i}" for i in range(100)}
        cand = {f"user{i}" for i in range(90)}  # cand 쪽 90/90 이 base 와 겹침
        self.assertTrue(sbp.is_complement(base, cand))

    def test_does_not_flag_low_overlap(self):
        base = {f"user{i}" for i in range(100)}
        cand = {f"other{i}" for i in range(20)} | {"user0", "user1"}  # 2/20 만 겹침
        self.assertFalse(sbp.is_complement(base, cand))

    def test_missing_data_does_not_flag(self):
        """dependents 데이터가 없는 쪽은 판단하지 않고 통과시킨다(보수적 기본값) —
        후보 풀의 61.5%만 커버되던 시점의 실측 전제와 같음."""
        self.assertFalse(sbp.is_complement(None, {"a", "b"}))
        self.assertFalse(sbp.is_complement({"a", "b"}, None))
        self.assertFalse(sbp.is_complement(set(), {"a", "b"}))

    def test_threshold_is_configurable(self):
        base = {"a", "b", "c", "d"}
        cand = {"a", "b"}  # 비율 2/2 = 1.0
        # min_sample 기본값(20)보다 작은 집합이라 표본 부족 판정과 섞이지 않게
        # min_sample=1 로 threshold 자체의 동작만 분리해서 검증한다.
        self.assertFalse(sbp.is_complement(base, cand, threshold=1.5, min_sample=1))
        self.assertTrue(sbp.is_complement(base, cand, threshold=0.3, min_sample=1))

    def test_small_sample_does_not_flag_even_with_high_ratio(self):
        """실측(2026-09-16)에서 찾은 노이즈 사례 반영 — jest(dependents 11,228개) vs
        @japa/runner(dependents 7개)가 우연히 4개 겹쳐 비율 0.571로 나왔지만, 표본이
        7개뿐이라 통계적으로 못 믿을 수치다. 둘 중 작은 쪽이 min_sample 미만이면
        비율이 아무리 높아도 판단을 보류(통과)한다."""
        base = {f"user{i}" for i in range(11228)}
        cand = {f"user{i}" for i in range(4)} | {"only-in-cand-1", "only-in-cand-2", "only-in-cand-3"}
        self.assertEqual(len(cand), 7)
        self.assertFalse(sbp.is_complement(base, cand))  # 비율 4/7=0.571 이지만 표본 부족

    def test_sample_at_or_above_min_sample_is_judged_normally(self):
        base = {f"user{i}" for i in range(100)}
        cand = {f"user{i}" for i in range(20)}  # 정확히 min_sample 기본값(20), 비율 1.0
        self.assertTrue(sbp.is_complement(base, cand))

    def test_min_sample_is_configurable(self):
        base = {f"user{i}" for i in range(100)}
        cand = {f"user{i}" for i in range(7)}  # 비율 1.0 이지만 표본 7개
        self.assertFalse(sbp.is_complement(base, cand))  # 기본 min_sample=20 이라 보류
        self.assertTrue(sbp.is_complement(base, cand, min_sample=5))  # 낮추면 판단함


class ApplyGates(unittest.TestCase):
    NAMES = ["moment", "dayjs", "moment-timezone", "eslint-plugin-x", "luxon", "date-fns"]
    KW = {i: [] for i in range(6)}
    ARCHIVED = {i: False for i in range(6)}
    HITS = [(0, 1, 0.9), (0, 2, 0.8), (0, 3, 0.7), (0, 4, 0.6), (0, 5, 0.5)]

    def test_disabled_returns_hits_unchanged(self):
        kept, drops = sbp.apply_gates(self.HITS, self.NAMES, self.KW, enabled=False)
        self.assertEqual(kept, self.HITS)
        self.assertEqual(drops, {})

    def test_drops_plugin_candidate(self):
        kept, drops = sbp.apply_gates(self.HITS, self.NAMES, self.KW, enabled=True)
        self.assertNotIn(3, [c for _, c, _ in kept])
        self.assertEqual(drops["plugin_adapter"], 1)

    def test_drops_same_family_candidate(self):
        kept, drops = sbp.apply_gates(self.HITS, self.NAMES, self.KW, enabled=True)
        self.assertNotIn(2, [c for _, c, _ in kept])  # moment-timezone
        self.assertEqual(drops["same_family"], 1)

    def test_keeps_genuine_alternatives(self):
        kept, _ = sbp.apply_gates(self.HITS, self.NAMES, self.KW, enabled=True)
        self.assertEqual([c for _, c, _ in kept], [1, 4, 5])  # dayjs, luxon, date-fns

    def test_drops_via_keyword_signal(self):
        kw = {**self.KW, 1: ["plugin"]}
        kept, drops = sbp.apply_gates([(0, 1, 0.9)], self.NAMES, kw, enabled=True)
        self.assertEqual(kept, [])
        self.assertEqual(drops["plugin_adapter"], 1)

    def test_drops_archived_candidate(self):
        archived = {**self.ARCHIVED, 5: True}  # date-fns 를 보관 처리된 것으로 가정
        kept, drops = sbp.apply_gates(
            self.HITS, self.NAMES, self.KW, enabled=True, archived_by_idx=archived
        )
        self.assertNotIn(5, [c for _, c, _ in kept])
        self.assertEqual(drops["repo_archived"], 1)

    def test_no_archived_by_idx_keeps_previous_behavior(self):
        """archived_by_idx 를 안 주면(옛 호출부) 아무도 archived 로 안 걸린다."""
        kept, drops = sbp.apply_gates(self.HITS, self.NAMES, self.KW, enabled=True)
        self.assertEqual([c for _, c, _ in kept], [1, 4, 5])
        self.assertNotIn("repo_archived", drops)

    def test_drops_complement_candidate(self):
        """S15P21A506-173: dependents 겹침이 높은 후보(보완재)를 감점(=drop)한다."""
        dependents = {
            0: {f"user{i}" for i in range(100)},  # moment
            1: {f"user{i}" for i in range(90)},   # dayjs — moment 와 90% 겹침(보완재로 취급)
            4: {"other1", "other2"},              # luxon — 겹침 거의 없음(진짜 대안)
            5: {"other3", "other4"},              # date-fns
        }
        kept, drops = sbp.apply_gates(
            self.HITS, self.NAMES, self.KW, enabled=True, dependents_by_idx=dependents
        )
        self.assertNotIn(1, [c for _, c, _ in kept])
        self.assertEqual(drops["complement"], 1)

    def test_no_dependents_by_idx_keeps_previous_behavior(self):
        """dependents_by_idx 를 안 주면(옛 호출부) 아무도 complement 로 안 걸린다."""
        kept, drops = sbp.apply_gates(self.HITS, self.NAMES, self.KW, enabled=True)
        self.assertEqual([c for _, c, _ in kept], [1, 4, 5])

    def test_complement_is_none_when_gate_did_not_run(self):
        """dependents 가 없어 관문이 안 돌았으면 0 이 아니라 None — '0건 걸렀다' 와 구분된다."""
        _, drops = sbp.apply_gates(self.HITS, self.NAMES, self.KW, enabled=True)
        self.assertIn("complement", drops)
        self.assertIsNone(drops["complement"])

    def test_complement_is_zero_when_gate_ran_but_nothing_dropped(self):
        dependents = {0: {"a"}, 1: {"b"}, 4: {"c"}, 5: {"d"}}
        _, drops = sbp.apply_gates(
            self.HITS, self.NAMES, self.KW, enabled=True, dependents_by_idx=dependents
        )
        self.assertEqual(drops["complement"], 0)


class ApplyDownloadsFloor(unittest.TestCase):
    """S15P21A506-450: 인지도 관문."""

    HITS = [(0, 1, 0.9), (0, 2, 0.8), (0, 3, 0.7)]

    def test_floor_zero_keeps_hits_unchanged(self):
        kept, dropped = sbp.apply_downloads_floor(self.HITS, {1: 10, 2: 20, 3: 30}, floor=0)
        self.assertEqual(kept, self.HITS)
        self.assertEqual(dropped, 0)

    def test_drops_candidate_below_floor(self):
        downloads = {1: 1_000_000, 2: 100, 3: 600_000}
        kept, dropped = sbp.apply_downloads_floor(self.HITS, downloads, floor=500_000)
        self.assertEqual([c for _, c, _ in kept], [1, 3])
        self.assertEqual(dropped, 1)

    def test_missing_downloads_data_does_not_pass(self):
        """downloads 정보가 없는(None) 후보는 관대하게 통과시키지 않는다."""
        downloads = {1: 1_000_000, 2: None, 3: 600_000}
        kept, dropped = sbp.apply_downloads_floor(self.HITS, downloads, floor=500_000)
        self.assertEqual([c for _, c, _ in kept], [1, 3])
        self.assertEqual(dropped, 1)

    def test_candidate_not_in_map_treated_as_missing(self):
        downloads = {1: 1_000_000, 3: 600_000}  # 2 없음
        kept, dropped = sbp.apply_downloads_floor(self.HITS, downloads, floor=500_000)
        self.assertEqual([c for _, c, _ in kept], [1, 3])
        self.assertEqual(dropped, 1)

    def test_all_pass_when_all_above_floor(self):
        downloads = {1: 1_000_000, 2: 2_000_000, 3: 3_000_000}
        kept, dropped = sbp.apply_downloads_floor(self.HITS, downloads, floor=500_000)
        self.assertEqual(kept, self.HITS)
        self.assertEqual(dropped, 0)


class ApplyDownloadsFloorWithFallback(unittest.TestCase):
    """S15P21A506-458: base 별로 3개 미만이면 하한을 단계적으로 완화한다."""

    TIERS = (500_000, 100_000, 50_000, 10_000, 0)

    def test_base_with_enough_at_strictest_tier_is_not_relaxed(self):
        """모든 후보가 최상위 하한을 이미 넘으면 완화가 필요 없다."""
        hits = [(0, 1, 0.9), (0, 2, 0.8), (0, 3, 0.7)]
        downloads = {1: 1_000_000, 2: 2_000_000, 3: 3_000_000}
        kept, tiers_used = sbp.apply_downloads_floor_with_fallback(hits, downloads, self.TIERS)
        self.assertEqual(kept, hits)
        self.assertEqual(tiers_used[500_000], 1)
        self.assertEqual(sum(tiers_used.values()), 1)

    def test_relaxes_to_next_tier_when_strictest_leaves_too_few(self):
        """50만 하한이면 1개만 남지만, 5만까지 낮추면 3개가 남는 경우."""
        hits = [(0, 1, 0.9), (0, 2, 0.8), (0, 3, 0.7)]
        downloads = {1: 600_000, 2: 80_000, 3: 60_000}
        kept, tiers_used = sbp.apply_downloads_floor_with_fallback(hits, downloads, self.TIERS)
        self.assertEqual({c for _, c, _ in kept}, {1, 2, 3})
        self.assertEqual(tiers_used[50_000], 1)
        self.assertEqual(tiers_used[500_000], 0)

    def test_falls_through_to_last_tier_even_if_still_under_min_kept(self):
        """맨 끝(0)까지 가도 3개가 안 채워지면, 그 결과라도(2개든 0개든) 그대로 쓴다."""
        hits = [(0, 1, 0.9), (0, 2, 0.8)]  # 애초에 구조적 관문 통과분이 2개뿐
        downloads = {1: 5_000, 2: 3_000}
        kept, tiers_used = sbp.apply_downloads_floor_with_fallback(hits, downloads, self.TIERS)
        self.assertEqual({c for _, c, _ in kept}, {1, 2})
        self.assertEqual(tiers_used[0], 1)

    def test_each_base_relaxes_independently(self):
        hits = [
            (0, 1, 0.9), (0, 2, 0.8), (0, 3, 0.7),  # base 0: 전부 인기 있음 -> 안 완화
            (5, 6, 0.9), (5, 7, 0.8), (5, 8, 0.7),  # base 5: 인기 없음 -> 완화 필요
        ]
        downloads = {1: 1_000_000, 2: 1_000_000, 3: 1_000_000, 6: 5_000, 7: 4_000, 8: 3_000}
        kept, tiers_used = sbp.apply_downloads_floor_with_fallback(hits, downloads, self.TIERS)
        self.assertEqual({c for b, c, _ in kept if b == 0}, {1, 2, 3})
        self.assertEqual({c for b, c, _ in kept if b == 5}, {6, 7, 8})
        self.assertEqual(tiers_used[500_000], 1)
        self.assertEqual(tiers_used[0], 1)

    def test_min_kept_is_configurable(self):
        hits = [(0, 1, 0.9), (0, 2, 0.8)]
        downloads = {1: 1_000_000, 2: 100}
        kept, tiers_used = sbp.apply_downloads_floor_with_fallback(
            hits, downloads, self.TIERS, min_kept=1
        )
        self.assertEqual([c for _, c, _ in kept], [1])
        self.assertEqual(tiers_used[500_000], 1)

    def test_empty_hits_returns_empty(self):
        kept, tiers_used = sbp.apply_downloads_floor_with_fallback([], {}, self.TIERS)
        self.assertEqual(kept, [])
        self.assertEqual(sum(tiers_used.values()), 0)


class ResolveDependentsPath(unittest.TestCase):
    """S15P21A506-173: --dependents 를 안 줘도 --package-text 옆 파일이 있으면 관문이 돈다."""

    def test_explicit_path_wins_even_if_missing(self):
        self.assertEqual(sbp.resolve_dependents_path("x/dep.parquet", "in/package_text.parquet"), "x/dep.parquet")

    def test_finds_sibling_next_to_package_text(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            sibling = os.path.join(d, sbp.DEPENDENTS_FILENAME)
            open(sibling, "wb").close()
            got = sbp.resolve_dependents_path(None, os.path.join(d, "package_text.parquet"))
            self.assertEqual(os.path.abspath(got), os.path.abspath(sibling))

    def test_none_when_no_sibling(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(sbp.resolve_dependents_path(None, os.path.join(d, "package_text.parquet")))


class DependentsCoverage(unittest.TestCase):
    def test_none_when_no_dependents_given(self):
        self.assertIsNone(sbp.dependents_coverage(["a", "b"], {}))

    def test_counts_names_present_in_map(self):
        cov = sbp.dependents_coverage(["a", "b", "c", "d"], {"a": {"x"}, "c": {"y"}, "zzz": {"q"}})
        self.assertEqual(cov, {"pool": 4, "with_dependents": 2, "ratio": 0.5})

    def test_empty_dependents_set_still_counts_as_covered(self):
        """의존자 0개는 결측이 아니라 범주라 행이 있으면 센다."""
        cov = sbp.dependents_coverage(["a", "b"], {"a": set(), "b": {"x"}})
        self.assertEqual(cov["with_dependents"], 2)
        self.assertEqual(cov["ratio"], 1.0)

    def test_empty_pool_does_not_divide_by_zero(self):
        cov = sbp.dependents_coverage([], {"a": {"x"}})
        self.assertEqual(cov, {"pool": 0, "with_dependents": 0, "ratio": 0.0})


class LoadPackageText(QuietMixin, unittest.TestCase):
    """읽기 단계 예선 필터가 qualify() 의 dependents 규칙과 어긋나지 않는지 (S15P21A506-382).

    이 시험이 깨지면 **코퍼스가 조용히 줄었다**는 뜻이다. 예선 필터는 오류를 내지
    않고 행을 덜 읽을 뿐이라, 어긋나도 배치는 정상 종료하고 후보만 적어진다.
    걸릴 만한 자리는 둘이다 — 나중에 누가 예선 필터에 조건을 더 얹는 것, 그리고
    pyarrow 갱신으로 `>=` 의 null 취급이 달라지는 것.
    """

    ROWS = {
        # dep, 최신 릴리스, status, is_spam — qualify 가 보는 네 열
        "keep_high": (10, "2026-09-01", None, False),
        "keep_exact": (5, "2026-09-01", None, False),        # 경계: 하한과 같으면 통과
        "keep_null_date": (7, None, None, False),            # 날짜 null 은 qualify 가 남긴다
        "drop_low": (4, "2026-09-01", None, False),          # 경계: 하한 미만
        "drop_null_dep": (None, "2026-09-01", None, False),  # dep null 은 양쪽 다 버린다
        "drop_old": (9, "2000-01-01", None, False),          # qualify 가 버린다
        "drop_deprecated": (9, "2026-09-01", "deprecated", False),
        "drop_spam": (9, "2026-09-01", None, True),
    }

    def _write(self, path):
        import pyarrow as pa
        import pyarrow.parquet as pq

        names = list(self.ROWS)
        pq.write_table(
            pa.table({
                "name": names,
                "description": [f"desc of {n}" for n in names],
                "keywords": [["kw"] for _ in names],
                "dependent_packages_count": [self.ROWS[n][0] for n in names],
                "latest_release_published_at": [self.ROWS[n][1] for n in names],
                "status": [self.ROWS[n][2] for n in names],
                "is_spam": [self.ROWS[n][3] for n in names],
                # 이 클래스의 시험은 dependents 규칙만 본다 — 전부 고정 목록 안(1)으로 두어
                # download_rank 기본 컷(100000)에 걸리지 않게 한다. download_rank 자체를
                # 다루는 시험은 아래 _write_ranked 를 쓴다.
                "download_rank": [1] * len(names),
            }),
            path,
        )

    def test_prefilter_drops_below_threshold_and_null_dependents(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "package_text.parquet")
            self._write(path)
            got = {r["name"] for r in sbp.load_package_text(path, 5)}
        self.assertNotIn("drop_low", got)
        self.assertNotIn("drop_null_dep", got)
        self.assertIn("keep_exact", got)   # 하한과 같은 값은 통과한다
        # 예선 필터는 dependents 만 본다 — 나머지 판정은 qualify 몫이라 여기서는 살아 있다
        self.assertIn("drop_old", got)
        self.assertIn("drop_deprecated", got)

    def test_prefilter_then_qualify_equals_full_load_then_qualify(self):
        """예선 필터를 거친 뒤 qualify 한 결과가, 전수를 읽고 qualify 한 것과 같아야 한다."""
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "package_text.parquet")
            self._write(path)
            prefiltered = sbp.qualify(sbp.load_package_text(path, 5), 5, 12)
            full = sbp.qualify(pq.read_table(path).to_pylist(), 5, 12)

        # 순서까지 같아야 한다. top_k 가 행 순서를 색인으로 쓴다
        self.assertEqual([r["name"] for r in prefiltered], [r["name"] for r in full])
        self.assertEqual(
            [r["name"] for r in prefiltered],
            ["keep_high", "keep_exact", "keep_null_date"],
        )

    def test_order_preserved_across_row_groups(self):
        """row group 이 여럿일 때도 읽은 순서가 파일 순서와 같아야 한다.

        위 시험의 파일은 8행 단일 row group 이라 이 성질을 건드리지 못한다. 실제
        코퍼스는 `build_package_text.py` 가 100,000행마다 끊어 쓰므로 92만 행이면
        열 개 안팎이 된다. 읽기 필터가 row group 을 병렬로 읽고 순서를 섞으면
        여기서 걸린다.
        """
        import pyarrow as pa
        import pyarrow.parquet as pq

        n = 50
        names = [f"p{i:03d}" for i in range(n)]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "package_text.parquet")
            pq.write_table(
                pa.table({
                    "name": names,
                    "description": ["d" for _ in names],
                    "keywords": [["kw"] for _ in names],
                    # 짝수만 통과시켜, 섞였을 때 눈에 띄게 한다
                    "dependent_packages_count": [10 if i % 2 == 0 else 1 for i in range(n)],
                    "latest_release_published_at": ["2026-09-01" for _ in names],
                    "status": [None for _ in names],
                    "is_spam": [False for _ in names],
                    "download_rank": [1] * n,
                }),
                path,
                row_group_size=7,   # 50행 / 7 = row group 8개
            )
            self.assertGreater(pq.read_metadata(path).num_row_groups, 1)
            got = [r["name"] for r in sbp.load_package_text(path, 5)]

        self.assertEqual(got, [f"p{i:03d}" for i in range(n) if i % 2 == 0])

    def _write_ranked(self, path, ranks, deps=None):
        """download_rank 를 채운 parquet. `ranks` 의 각 값이 그대로 download_rank 가 된다 —
        고정 목록(rank_top100k_20260902.csv) 조인 결과를 흉내낸다(build_package_text.py 참고)."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        names = [f"p{i}" for i in range(len(ranks))]
        pq.write_table(
            pa.table({
                "name": names,
                "download_rank": pa.array(ranks, type=pa.int64()),
                "description": ["d" for _ in names],
                "keywords": [["kw"] for _ in names],
                "dependent_packages_count": deps if deps is not None else [10] * len(names),
                "latest_release_published_at": ["2026-09-01" for _ in names],
                "status": [None for _ in names],
                "is_spam": [False for _ in names],
            }),
            path,
        )

    def test_max_rank_cuts_at_boundary_inclusive(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "package_text.parquet")
            self._write_ranked(path, [1, 2, 3, 4, 5])
            got = [r["name"] for r in sbp.load_package_text(path, 5, max_rank=3)]
        self.assertEqual(got, ["p0", "p1", "p2"])   # download_rank 3 은 포함, 4 부터 제외

    def test_max_rank_omitted_still_cuts_at_default_100000(self):
        """옵션을 아예 안 줘도 100000 밖(NULL 포함)은 통과 못 한다 — S15P21A506-402 의 핵심.

        이전에는 --max-rank 를 빼먹으면(None) 컷 자체가 꺼져 리포트 데이터 없는 패키지가
        후보로 다시 섞였다. 이제는 옵션을 잊어도 안전해야 한다.
        """
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "package_text.parquet")
            self._write_ranked(path, [1, 100000, 100001, None])
            got = {r["name"] for r in sbp.load_package_text(path, 5)}   # max_rank 인자 생략
        self.assertEqual(got, {"p0", "p1"})
        self.assertNotIn("p2", got)   # 100001 — 목록 상한 밖
        self.assertNotIn("p3", got)   # NULL — 애초에 목록에 없음

    def test_max_rank_counts_rows_not_rank_value_when_ranks_have_gaps(self):
        """상위 목록에서 이름이 하나 빠지면 download_rank 값에도 결번이 생긴다 —
        컷은 N 행이 아니라 download_rank<=N 이다."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "package_text.parquet")
            self._write_ranked(path, [1, 2, 4, 5, 7])   # 3, 6 결번
            got = [r["name"] for r in sbp.load_package_text(path, 5, max_rank=5)]
        self.assertEqual(got, ["p0", "p1", "p2", "p3"])   # 4행 — 5행이 아니다

    def test_max_rank_drops_null_rank(self):
        """download_rank NULL = 고정 목록 밖 = 리포트 불가. 상한을 아무리 키워도 통과 못 한다."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "package_text.parquet")
            self._write_ranked(path, [1, None, 3])
            got = [r["name"] for r in sbp.load_package_text(path, 5, max_rank=10)]
        self.assertEqual(got, ["p0", "p2"])

    def test_max_rank_intersects_with_dependents_floor(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "package_text.parquet")
            # download_rank 2 는 dependents 미달, download_rank 4 는 상한 초과 — 둘 다 빠지고 1·3 만 남는다
            self._write_ranked(path, [1, 2, 3, 4], deps=[10, 4, 10, 10])
            got = [r["name"] for r in sbp.load_package_text(path, 5, max_rank=3)]
        self.assertEqual(got, ["p0", "p2"])

    def test_max_rank_preserves_order_across_row_groups(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        n = 40
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "package_text.parquet")
            pq.write_table(
                pa.table({
                    "name": [f"p{i:03d}" for i in range(n)],
                    "download_rank": pa.array(list(range(1, n + 1)), type=pa.int64()),
                    "description": ["d"] * n,
                    "keywords": [["kw"]] * n,
                    "dependent_packages_count": [10] * n,
                    "latest_release_published_at": ["2026-09-01"] * n,
                    "status": [None] * n,
                    "is_spam": [False] * n,
                }),
                path,
                row_group_size=6,
            )
            self.assertGreater(pq.read_metadata(path).num_row_groups, 1)
            got = [r["name"] for r in sbp.load_package_text(path, 5, max_rank=25)]
        self.assertEqual(got, [f"p{i:03d}" for i in range(25)])

    def test_missing_download_rank_column_raises_clear_error(self):
        """download_rank 없는(구버전) package_text 를 넣으면 조용히 다 통과시키지 않고 즉시 에러."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "package_text.parquet")
            pq.write_table(
                pa.table({
                    "name": ["p0"],
                    "rank": pa.array([1], type=pa.int64()),   # 구버전 컬럼만 있고 download_rank 없음
                    "description": ["d"],
                    "keywords": [["kw"]],
                    "dependent_packages_count": [10],
                    "latest_release_published_at": ["2026-09-01"],
                    "status": [None],
                    "is_spam": [False],
                }),
                path,
            )
            with self.assertRaises(ValueError):
                sbp.load_package_text(path, 5)


class ParseArgs(unittest.TestCase):
    BASE = ["--package-text", "x", "--model-dir", "y", "--out", "z"]

    def test_max_rank_defaults_to_100000(self):
        """생략해도 컷이 꺼지지 않는다 — S15P21A506-402."""
        self.assertEqual(sbp.parse_args(self.BASE).max_rank, 100000)

    def test_max_rank_parsed(self):
        self.assertEqual(sbp.parse_args(self.BASE + ["--max-rank", "50000"]).max_rank, 50000)

    def test_retrieve_k_defaults_to_30(self):
        self.assertEqual(sbp.parse_args(self.BASE).retrieve_k, 30)

    def test_retrieve_k_parsed(self):
        self.assertEqual(sbp.parse_args(self.BASE + ["--retrieve-k", "50"]).retrieve_k, 50)

    def test_gate_defaults_on(self):
        self.assertTrue(sbp.parse_args(self.BASE).gate)

    def test_no_gate_turns_it_off(self):
        self.assertFalse(sbp.parse_args(self.BASE + ["--no-gate"]).gate)

    def test_downloads_floor_defaults_to_500000(self):
        """S15P21A506-450: 실측으로 채택된 기본값."""
        self.assertEqual(sbp.parse_args(self.BASE).downloads_floor, 500_000)

    def test_downloads_floor_parsed(self):
        self.assertEqual(
            sbp.parse_args(self.BASE + ["--downloads-floor", "100000"]).downloads_floor, 100000
        )

    def test_dependents_defaults_to_none(self):
        """S15P21A506-173: 안 주면 보완재 관문이 자동으로 꺼진다(옛 호출부 호환)."""
        self.assertIsNone(sbp.parse_args(self.BASE).dependents)

    def test_dependents_parsed(self):
        self.assertEqual(
            sbp.parse_args(self.BASE + ["--dependents", "dep.parquet"]).dependents, "dep.parquet"
        )


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
