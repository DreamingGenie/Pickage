"""generate() 유닛테스트 (S15P21A506-178, unittest, stdlib).

실제 OpenAI 호출은 하지 않는다 — llm_call을 주입해서 순수 로직(요청 구성·응답 파싱)만
검증한다. 실제 API 연결은 이 테스트의 책임이 아니다.

실행: 저장소 루트에서
    python -m unittest ai.rag.test_generation -v
"""

from __future__ import annotations

import io
import json
import os
import socket
import unittest
import urllib.error
from unittest import mock

from ai.rag.generation import (
    PROMPT,
    GmsCallError,
    GmsTimeoutError,
    _call_gms,
    _build_gms_request_body,
    _RESPONSE_JSON_SCHEMA,
    _extract_gms_output_text,
    build_user_message,
    generate,
)
from ai.rag.types import EvidenceChunk, Mark, PackageRef, PackageSource


def _make_evidence(evidence_id: str, package: str, version: str) -> EvidenceChunk:
    return EvidenceChunk(
        evidence_id=evidence_id,
        snapshot_id="snap-1",
        package=package,
        version=version,
        section="Usage",
        excerpt="지원합니다.",
        confirmed_content="지원합니다.",
    )


class GenerateHappyPathTests(unittest.TestCase):
    def test_calls_llm_with_prompt_and_parses_response(self):
        packages = [PackageRef(name="foo", version="1.0.0"), PackageRef(name="bar", version="2.0.0")]
        evidence = [
            _make_evidence("foo@1.0.0#0", "foo", "1.0.0"),
            _make_evidence("bar@2.0.0#0", "bar", "2.0.0"),
        ]
        recorded_calls = []

        fake_response = {
            "dataStatus": "COMPLETE",
            "common": "  둘 다 설정 파일을 읽어요.  ",
            "differences": [
                {
                    "package": "foo",
                    "version": "1.0.0",
                    "body": "foo 는 파일로 설정해요. 코드로도 설정할 수 있어요.",
                    "key_sentence": "foo 는 파일로 설정해요.",
                    "key_terms": ["파일로 설정"],
                },
                {
                    "package": "bar",
                    "version": "2.0.0",
                    "body": "bar 는 코드로 설정해요.",
                    "key_sentence": "",
                    "key_terms": [],
                },
            ],
        }

        def fake_llm_call(system_prompt: str, user_message: str) -> str:
            recorded_calls.append((system_prompt, user_message))
            return json.dumps(fake_response)

        result = generate(packages, evidence, llm_call=fake_llm_call)

        self.assertEqual(len(recorded_calls), 1)
        called_system_prompt, called_user_message = recorded_calls[0]
        self.assertEqual(called_system_prompt, PROMPT)
        self.assertEqual(called_user_message, build_user_message(packages, evidence))

        self.assertEqual(result.data_status, "COMPLETE")
        # packages 는 모델이 아니라 요청에서 온다
        self.assertEqual([p.name for p in result.packages], ["foo", "bar"])
        self.assertEqual(result.common, "둘 다 설정 파일을 읽어요.")
        self.assertEqual([d.package for d in result.differences], ["foo", "bar"])
        self.assertEqual(result.differences[1].body, "bar 는 코드로 설정해요.")
        # key_sentence/key_terms 는 body 안에서 찾아 marks 로 계산된다(S15P21A506-470). 위치는
        # 서버가 계산한다 — 모델이 준 값을 쓰지 않는다.
        body = result.differences[0].body
        sentence_start = body.index("foo 는 파일로 설정해요.")
        term_start = body.index("파일로 설정")
        self.assertEqual(
            result.differences[0].marks,
            [
                Mark(start=sentence_start, end=sentence_start + 15, kind="KEY_SENTENCE"),
                Mark(start=term_start, end=term_start + 6, kind="KEY_TERM"),
            ],
        )
        self.assertEqual(result.differences[1].marks, [])


class ResponseSchemaTests(unittest.TestCase):
    def test_schema_asks_only_for_common_and_per_package_differences(self):
        self.assertEqual(
            set(_RESPONSE_JSON_SCHEMA["properties"]), {"dataStatus", "common", "differences"}
        )
        item = _RESPONSE_JSON_SCHEMA["properties"]["differences"]["items"]
        self.assertEqual(
            set(item["properties"]), {"package", "version", "body", "key_sentence", "key_terms"}
        )
        self.assertEqual(item["properties"]["key_terms"]["maxItems"], 3)


class DifferenceMarksTests(unittest.TestCase):
    """key_sentence/key_terms → marks 계산 (S15P21A506-470)."""

    def _generate(self, key_sentence, key_terms, body="foo 는 파일로 설정해요."):
        packages = [PackageRef(name="foo", version="1.0.0")]
        evidence = [_make_evidence("foo@1.0.0#0", "foo", "1.0.0")]

        def fake_llm(system_prompt, user_message):
            return json.dumps(
                {
                    "dataStatus": "COMPLETE",
                    "common": "공통",
                    "differences": [
                        {
                            "package": "foo",
                            "version": "1.0.0",
                            "body": body,
                            "key_sentence": key_sentence,
                            "key_terms": key_terms,
                        }
                    ],
                }
            )

        return generate(packages, evidence, llm_call=fake_llm).differences[0]

    def test_body_not_matching_substrings_are_discarded_without_failing(self):
        note = self._generate("요약문에 전혀 없는 문장이다.", ["없는 말"])

        self.assertEqual(note.marks, [])
        self.assertEqual(note.body, "foo 는 파일로 설정해요.")

    def test_prompt_asks_for_verbatim_key_sentence_and_key_terms(self):
        self.assertIn("key_sentence", PROMPT)
        self.assertIn("key_terms", PROMPT)
        self.assertIn("character for character", PROMPT)


class BuildGmsRequestBodyTests(unittest.TestCase):
    def test_uses_role_separated_input_and_json_schema_strict_format(self):
        body = _build_gms_request_body("SYSTEM TEXT", "USER TEXT", model="gpt-5.1")

        self.assertEqual(body["model"], "gpt-5.1")
        self.assertEqual(
            body["input"],
            [
                {"role": "system", "content": "SYSTEM TEXT"},
                {"role": "user", "content": "USER TEXT"},
            ],
        )
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertIn("schema", body["text"]["format"])


class ExtractGmsOutputTextTests(unittest.TestCase):
    def test_extracts_text_from_completed_envelope(self):
        envelope = json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"dataStatus":"COMPLETE"}'}],
                    }
                ],
            }
        )

        text = _extract_gms_output_text(envelope)

        self.assertEqual(text, '{"dataStatus":"COMPLETE"}')

    def test_raises_when_status_is_not_completed(self):
        envelope = json.dumps({"status": "incomplete", "output": []})

        with self.assertRaises(GmsCallError):
            _extract_gms_output_text(envelope)

    def test_raises_when_no_output_text_found(self):
        envelope = json.dumps({"status": "completed", "output": []})

        with self.assertRaises(GmsCallError):
            _extract_gms_output_text(envelope)


_GMS_ENV = {
    "GMS_API_KEY": "k",
    "GMS_BASE_URL": "https://gms.example",
    "GMS_REQUEST_PATH": "/v1/responses",
    "GMS_AUTH_HEADER": "Authorization",
    "GMS_AUTH_SCHEME": "Bearer",
    "GMS_MODEL": "gpt-5.1",
}
_OK_ENVELOPE = json.dumps(
    {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "PAYLOAD"}]}]}
)


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body.encode("utf-8")


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://gms.example", code, "err", {}, io.BytesIO(b'{"message":"x"}'))


@mock.patch.dict(os.environ, _GMS_ENV)
@mock.patch("ai.rag.generation.time.sleep")
class CallGmsTests(unittest.TestCase):
    """GMS 호출의 재시도·오류 변환 (S15P21A506-484)."""

    def test_retries_on_429_then_succeeds(self, sleep):
        with mock.patch("urllib.request.urlopen", side_effect=[_http_error(429), _FakeResponse(_OK_ENVELOPE)]) as urlopen:
            text = _call_gms("sys", "user")

        self.assertEqual(text, "PAYLOAD")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once()

    def test_gives_up_after_two_retries_on_persistent_5xx(self, sleep):
        with mock.patch("urllib.request.urlopen", side_effect=[_http_error(503)] * 3) as urlopen:
            with self.assertRaises(GmsCallError):
                _call_gms("sys", "user")

        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_does_not_retry_on_client_error(self, sleep):
        with mock.patch("urllib.request.urlopen", side_effect=[_http_error(400)]) as urlopen:
            with self.assertRaises(GmsCallError):
                _call_gms("sys", "user")

        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    def test_timeout_becomes_gms_timeout_error_without_retry(self, sleep):
        for exc in (socket.timeout("timed out"), urllib.error.URLError(socket.timeout("timed out"))):
            with self.subTest(exc=type(exc).__name__):
                with mock.patch("urllib.request.urlopen", side_effect=[exc]) as urlopen:
                    with self.assertRaises(GmsTimeoutError):
                        _call_gms("sys", "user")
                self.assertEqual(urlopen.call_count, 1)

    def test_network_error_becomes_gms_call_error(self, sleep):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with self.assertRaises(GmsCallError) as ctx:
                _call_gms("sys", "user")

        self.assertNotIsInstance(ctx.exception, GmsTimeoutError)

    def test_malformed_envelope_becomes_gms_call_error(self, sleep):
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse("not json")):
            with self.assertRaises(GmsCallError):
                _call_gms("sys", "user")


class MalformedModelOutputTests(unittest.TestCase):
    def test_non_json_model_output_becomes_gms_call_error(self):
        with self.assertRaises(GmsCallError):
            generate([PackageRef("a", "1")], [], llm_call=lambda s, u: "not json")

    def test_missing_fields_in_model_output_become_gms_call_error(self):
        with self.assertRaises(GmsCallError):
            generate([PackageRef("a", "1")], [], llm_call=lambda s, u: json.dumps({"dataStatus": "COMPLETE"}))


class DocumentStatusMessageTests(unittest.TestCase):
    """문헌 상태를 프롬프트 입력에 싣는다 (S15P21A506-419)."""

    def _packages(self):
        return [PackageRef(name="foo", version="1.0.0"), PackageRef(name="bar", version="2.0.0")]

    def test_document_status_is_added_only_when_sources_are_given(self):
        evidence = [_make_evidence("foo@1.0.0#0", "foo", "1.0.0")]
        sources = [
            PackageSource("foo", "1.0.0", "LIMITED"),
            PackageSource("bar", "2.0.0", "OK"),
        ]

        without = json.loads(build_user_message(self._packages(), evidence))
        with_status = json.loads(build_user_message(self._packages(), evidence, sources=sources))

        self.assertNotIn("documentStatus", without)
        self.assertEqual(
            with_status["documentStatus"],
            [
                {"package": "foo", "version": "1.0.0", "status": "LIMITED"},
                {"package": "bar", "version": "2.0.0", "status": "OK"},
            ],
        )

    def test_packages_with_an_unknown_status_are_left_out(self):
        evidence = [_make_evidence("foo@1.0.0#0", "foo", "1.0.0")]
        sources = [PackageSource("foo", "1.0.0"), PackageSource("bar", "2.0.0", "NONE")]

        message = json.loads(build_user_message(self._packages(), evidence, sources=sources))

        self.assertEqual(message["documentStatus"], [{"package": "bar", "version": "2.0.0", "status": "NONE"}])

    def test_no_known_status_means_no_key_at_all(self):
        evidence = [_make_evidence("foo@1.0.0#0", "foo", "1.0.0")]

        message = json.loads(
            build_user_message(self._packages(), evidence, sources=[PackageSource("foo", "1.0.0")])
        )

        self.assertNotIn("documentStatus", message)

    def test_prompt_tells_the_model_not_to_read_a_short_readme_as_a_missing_feature(self):
        self.assertIn("documentStatus", PROMPT)
        self.assertIn("LIMITED", PROMPT)

    def test_generate_passes_the_status_through_to_the_model_input(self):
        packages = [PackageRef(name="foo", version="1.0.0")]
        evidence = [_make_evidence("foo@1.0.0#0", "foo", "1.0.0")]
        seen = []

        def fake_llm(system_prompt, user_message):
            seen.append(user_message)
            return json.dumps(
                {"dataStatus": "COMPLETE", "common": "공통",
                 "differences": [{"package": "foo", "version": "1.0.0", "body": "차이"}]}
            )

        generate(packages, evidence, llm_call=fake_llm, sources=[PackageSource("foo", "1.0.0", "LIMITED")])

        self.assertIn("LIMITED", seen[0])



class MetaEvidenceMessageTests(unittest.TestCase):
    """헤더 근거를 모델이 근거로 알아보게 한다 (S15P21A506-420)."""

    def test_every_evidence_item_carries_its_source_type(self):
        packages = [PackageRef(name="foo", version="1.0.0")]
        meta = _make_evidence("foo@1.0.0#meta-entry", "foo", "1.0.0")
        meta.source_type = "TARBALL_PACKAGE_JSON"
        readme = _make_evidence("foo@1.0.0#0", "foo", "1.0.0")

        message = json.loads(build_user_message(packages, [meta, readme]))

        self.assertEqual(
            [e["sourceType"] for e in message["evidence"]], ["TARBALL_PACKAGE_JSON", "TARBALL_README"]
        )

    def test_prompt_explains_package_metadata_and_keeps_environment_facts_out(self):
        self.assertIn("TARBALL_PACKAGE_JSON", PROMPT)
        self.assertIn("License", PROMPT)


class CompactInputTests(unittest.TestCase):
    """출력에 근거 ID 가 없으니 입력에서도 뺀다 — 입력 토큰을 줄인다 (2026-09-22)."""

    def test_evidence_items_carry_no_id_or_version(self):
        packages = [PackageRef(name="foo", version="1.0.0")]
        message = json.loads(build_user_message(packages, [_make_evidence("foo@1.0.0#0", "foo", "1.0.0")]))

        self.assertEqual(set(message["evidence"][0]), {"package", "section", "sourceType", "excerpt"})

    def test_only_supplementary_evidence_is_marked(self):
        packages = [PackageRef(name="foo", version="1.0.0")]
        noise = _make_evidence("foo@1.0.0#1", "foo", "1.0.0")
        noise.verification_level = "SUPPLEMENTARY"

        message = json.loads(build_user_message(packages, [_make_evidence("foo@1.0.0#0", "foo", "1.0.0"), noise]))

        self.assertNotIn("supplementary", message["evidence"][0])
        self.assertTrue(message["evidence"][1]["supplementary"])

    def test_message_has_no_indentation(self):
        packages = [PackageRef(name="foo", version="1.0.0")]
        self.assertNotIn("\n", build_user_message(packages, [_make_evidence("foo@1.0.0#0", "foo", "1.0.0")]))


class PromptRuleTests(unittest.TestCase):
    def test_prompt_asks_for_korean_plain_text(self):
        self.assertIn("Korean", PROMPT)
        self.assertIn("해요체", PROMPT)
        self.assertIn("no Markdown", PROMPT)

    def test_prompt_forbids_ranking_and_recommendation(self):
        for word in ("rank", "recommend", "추천"):
            with self.subTest(word=word):
                self.assertIn(word, PROMPT)

    def test_prompt_treats_excerpts_as_untrusted(self):
        self.assertIn("untrusted", PROMPT)


if __name__ == "__main__":
    unittest.main()
