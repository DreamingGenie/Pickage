import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.version_dependents import finalization_recovery


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_json(path, value):
    path.write_bytes(_json_bytes(value))


class FinalizationRecoveryTest(unittest.TestCase):
    def _fixture(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name).resolve()
        plan = {"format": "parallel", "partitions": {"0": {}, "1": {}},
                "generation_contract": {
                    "input": {"parallel_input_sha256": "a" * 64},
                    "production": {"weighted_quality_sha256": "b" * 64, "runner_sha256": "0" * 64},
                    "code": {
                        "historical_parallel": "c" * 64,
                        "historical_parallel_input": "d" * 64,
                        "finalization_recovery": "e" * 64,
                    },
                }}
        _write_json(root / "run_plan.json", plan)
        checkpoint_hashes = {}
        for number in (0, 1):
            path = root / "partitions" / f"{number:03d}" / "complete.json"
            path.parent.mkdir(parents=True)
            path.write_text(f"checkpoint-{number}\n", encoding="utf-8")
            checkpoint_hashes[f"partitions/{number:03d}/complete.json"] = file_sha256(path)
        current = json.loads(json.dumps(plan["generation_contract"]))
        current["input"]["parallel_input_sha256"] = "1" * 64
        current["production"]["weighted_quality_sha256"] = "2" * 64
        current["code"]["historical_parallel"] = "3" * 64
        current["code"]["historical_parallel_input"] = "4" * 64
        current["code"]["finalization_recovery"] = "5" * 64
        proof = {"format": "finalization-recovery-v1", "run_root": str(root),
                 "plan_sha256": file_sha256(root / "run_plan.json"),
                 "previous_contract": plan["generation_contract"], "new_contract": current,
                 "checkpoints": checkpoint_hashes,
                 "helper_sha256": file_sha256(Path(finalization_recovery.__file__))}
        proof_path = root / "proof.json"
        _write_json(proof_path, proof)
        return temp, root, plan, current, proof_path

    def test_accepts_pinned_reviewed_changes_and_all_checkpoints(self):
        temp, root, plan, current, proof_path = self._fixture()
        try:
            with mock.patch.dict("os.environ", {
                "PICKAGE_FINALIZATION_RECOVERY_PROOF": str(proof_path),
                "PICKAGE_FINALIZATION_RECOVERY_PROOF_SHA256": file_sha256(proof_path),
            }, clear=True):
                result = finalization_recovery.verify(root, plan, current)
            self.assertEqual(result, {"path": str(proof_path), "sha256": file_sha256(proof_path)})
        finally:
            temp.cleanup()

    def test_rejects_unreviewed_contract_change(self):
        temp, root, plan, current, proof_path = self._fixture()
        try:
            current["production"]["runner_sha256"] = "f" * 64
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["previous_contract"] = plan["generation_contract"]
            proof["new_contract"] = current
            _write_json(proof_path, proof)
            with mock.patch.dict("os.environ", {
                "PICKAGE_FINALIZATION_RECOVERY_PROOF": str(proof_path),
                "PICKAGE_FINALIZATION_RECOVERY_PROOF_SHA256": file_sha256(proof_path),
            }, clear=True), self.assertRaisesRegex(ValueError, "unreviewed"):
                finalization_recovery.verify(root, plan, current)
        finally:
            temp.cleanup()

    def test_rejects_missing_checkpoint_and_bad_checkpoint_sha(self):
        temp, root, plan, current, proof_path = self._fixture()
        try:
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["checkpoints"].pop("partitions/001/complete.json")
            _write_json(proof_path, proof)
            env = {
                "PICKAGE_FINALIZATION_RECOVERY_PROOF": str(proof_path),
                "PICKAGE_FINALIZATION_RECOVERY_PROOF_SHA256": file_sha256(proof_path),
            }
            with mock.patch.dict("os.environ", env, clear=True), self.assertRaisesRegex(ValueError, "coverage"):
                finalization_recovery.verify(root, plan, current)
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["checkpoints"]["partitions/001/complete.json"] = "0" * 64
            _write_json(proof_path, proof)
            env["PICKAGE_FINALIZATION_RECOVERY_PROOF_SHA256"] = file_sha256(proof_path)
            with mock.patch.dict("os.environ", env, clear=True), self.assertRaisesRegex(ValueError, "checkpoint SHA"):
                finalization_recovery.verify(root, plan, current)
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
