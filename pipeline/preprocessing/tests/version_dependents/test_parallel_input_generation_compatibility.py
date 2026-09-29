import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.version_dependents import historical_parallel_input as module


class ParallelInputGenerationCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="input-generation-proof-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "input_manifest.json").write_text("{}", encoding="utf-8")
        self.digest = "a" * 64
        self.old = copy.deepcopy(module.contract())
        self.current = copy.deepcopy(module.contract())
        self.old["parallel_input_sha256"] = "0" * 64
        self.old["base_input_contract"]["profile_generation"][module._READER_CONTRACT_PATH] = "1" * 64
        self.proof = self.root / "recovery-proof.json"

    def _configure(self, proof=None):
        proof = proof or {
            "format": module._RECOVERY_PROOF_FORMAT,
            "manifest_path": str((self.root / "input_manifest.json").resolve()),
            "manifest_sha256": self.digest,
            "previous_contract": self.old,
            "new_contract": self.current,
        }
        self.proof.write_text(json.dumps(proof, sort_keys=True), encoding="utf-8")
        return patch.dict(module.os.environ, {
            module._RECOVERY_PROOF_ENV: str(self.proof),
            module._RECOVERY_PROOF_SHA_ENV: file_sha256(self.proof),
        })

    def test_accepts_exact_pair_with_explicit_proof(self):
        with self._configure():
            self.assertTrue(module._compatible_generation(self.root, self.digest, self.old, self.current))

    def test_unconfigured_proof_is_not_compatible(self):
        with patch.dict(module.os.environ, {}, clear=True):
            self.assertFalse(module._compatible_generation(self.root, self.digest, self.old, self.current))

    def test_bad_proof_sha_is_rejected(self):
        with self._configure():
            with patch.dict(module.os.environ, {module._RECOVERY_PROOF_SHA_ENV: "f" * 64}):
                with self.assertRaisesRegex(ValueError, "proof SHA"):
                    module._compatible_generation(self.root, self.digest, self.old, self.current)

    def test_wrong_manifest_path_is_rejected(self):
        proof = {
            "format": module._RECOVERY_PROOF_FORMAT,
            "manifest_path": str((self.root / "other.json").resolve()),
            "manifest_sha256": self.digest,
            "previous_contract": self.old,
            "new_contract": self.current,
        }
        with self._configure(proof):
            with self.assertRaisesRegex(ValueError, "manifest mismatch"):
                module._compatible_generation(self.root, self.digest, self.old, self.current)

    def test_unapproved_contract_change_is_rejected(self):
        changed = copy.deepcopy(self.current)
        changed["validation_sha256"] = "f" * 64
        with self._configure({
            "format": module._RECOVERY_PROOF_FORMAT,
            "manifest_path": str((self.root / "input_manifest.json").resolve()),
            "manifest_sha256": self.digest,
            "previous_contract": self.old,
            "new_contract": changed,
        }):
            with self.assertRaisesRegex(ValueError, "unexpected generation changes"):
                module._compatible_generation(self.root, self.digest, self.old, changed)


if __name__ == "__main__":
    unittest.main()
