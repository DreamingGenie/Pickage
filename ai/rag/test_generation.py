"""generate() 유닛테스트 (S15P21A506-178, unittest, stdlib).

실제 OpenAI 호출은 하지 않는다 — llm_call을 주입해서 순수 로직(요청 구성·응답 파싱)만
검증한다. 실제 API 연결은 이 테스트의 책임이 아니다.

실행: 저장소 루트에서
    python -m unittest ai.rag.test_generation -v
"""

from __future__ import annotations

import json
import unittest

from ai.rag.generation import (
    PROMPT_A,
    GmsCallError,
    _build_gms_request_body,
    _extract_gms_output_text,
    build_user_message,
    generate,
)
from ai.rag.types import EvidenceChunk, PackageRef


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
    def test_calls_llm_with_prompt_a_and_parses_response(self):
        packages = [PackageRef(name="foo", version="1.0.0"), PackageRef(name="bar", version="2.0.0")]
        evidence = [
            _make_evidence("foo@1.0.0#0", "foo", "1.0.0"),
            _make_evidence("bar@2.0.0#0", "bar", "2.0.0"),
        ]
        recorded_calls = []

        fake_response = {
            "dataStatus": "COMPLETE",
            "packages": [
                {"package": "foo", "version": "1.0.0"},
                {"package": "bar", "version": "2.0.0"},
            ],
            "features": [
                {
                    "featureLabel": "구조화 JSON",
                    "results": [
                        {
                            "package": "foo",
                            "verdict": "SUPPORTED",
                            "evidenceIds": ["foo@1.0.0#0"],
                            "groundedIn": "EVIDENCE",
                            "note": "지원합니다.",
                        },
                        {
                            "package": "bar",
                            "verdict": "UNCONFIRMED",
                            "evidenceIds": [],
                            "groundedIn": "EVIDENCE",
                            "note": "",
                        },
                    ],
                }
            ],
            "narrative": [],
        }

        def fake_llm_call(system_prompt: str, user_message: str) -> str:
            recorded_calls.append((system_prompt, user_message))
            return json.dumps(fake_response)

        result = generate(packages, evidence, variant="A", llm_call=fake_llm_call)

        self.assertEqual(len(recorded_calls), 1)
        called_system_prompt, called_user_message = recorded_calls[0]
        self.assertEqual(called_system_prompt, PROMPT_A)
        self.assertEqual(called_user_message, build_user_message(packages, evidence))

        self.assertEqual(result.data_status, "COMPLETE")
        self.assertEqual(len(result.packages), 2)
        self.assertEqual(result.packages[0].name, "foo")
        self.assertEqual(len(result.features), 1)
        row = result.features[0]
        self.assertEqual(row.feature_label, "구조화 JSON")
        self.assertEqual(len(row.results), 2)
        self.assertEqual(row.results[0].package, "foo")
        self.assertEqual(row.results[0].verdict, "SUPPORTED")
        self.assertEqual(row.results[0].evidence_ids, ["foo@1.0.0#0"])
        self.assertEqual(row.results[1].verdict, "UNCONFIRMED")
        self.assertEqual(result.narrative, [])


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


if __name__ == "__main__":
    unittest.main()
