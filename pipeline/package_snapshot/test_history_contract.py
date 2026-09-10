"""Regression tests for the split history build and validator contracts."""

from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from . import history_contract


class HistoryContractTests(TestCase):
    def _change_source(self, filename, suffix):
        original_text = Path.read_text
        original_bytes = Path.read_bytes

        def read_text(path, *args, **kwargs):
            value = original_text(path, *args, **kwargs)
            return value + suffix if path.name == filename else value

        def read_bytes(path, *args, **kwargs):
            value = original_bytes(path, *args, **kwargs)
            return value + suffix.encode() if path.name == filename else value

        return patch.object(Path, 'read_text', read_text), patch.object(Path, 'read_bytes', read_bytes)

    def test_generator_change_invalidates_build_contract(self):
        baseline = history_contract.build_contract_sha256()
        for filename in ('history_build.py', 'history_inputs.py', 'history_policy.py',
                         'quality_schema.py', 'history.py'):
            with self.subTest(filename=filename):
                text_patch, bytes_patch = self._change_source(filename, '\n# changed generator\n')
                with text_patch, bytes_patch:
                    self.assertNotEqual(history_contract.build_contract_sha256(), baseline)

    def test_validator_change_does_not_invalidate_build_contract(self):
        build_baseline = history_contract.build_contract_sha256()
        validator_baseline = history_contract.validator_contract_sha256()
        text_patch, bytes_patch = self._change_source('history_load.py', '\n# changed validator\n')
        with text_patch, bytes_patch:
            self.assertEqual(history_contract.build_contract_sha256(), build_baseline)
            self.assertNotEqual(history_contract.validator_contract_sha256(), validator_baseline)

    def test_quality_validator_change_does_not_invalidate_build_contract(self):
        build_baseline = history_contract.build_contract_sha256()
        validator_baseline = history_contract.validator_contract_sha256()
        text_patch, bytes_patch = self._change_source('quality.py', '\n# changed validator\n')
        with text_patch, bytes_patch:
            self.assertEqual(history_contract.build_contract_sha256(), build_baseline)
            self.assertNotEqual(history_contract.validator_contract_sha256(), validator_baseline)

    def test_policy_document_change_invalidates_build_contract(self):
        baseline = history_contract.build_contract_sha256()
        original_policy = history_contract.policy_document

        def changed_policy():
            policy = dict(original_policy())
            policy['test_only_policy_change'] = True
            return policy

        with patch.object(history_contract, 'policy_document', new=changed_policy):
            self.assertNotEqual(history_contract.build_contract_sha256(), baseline)

    def test_load_and_postgres_changes_are_validator_only(self):
        build_baseline = history_contract.build_contract_sha256()
        validator_baseline = history_contract.validator_contract_sha256()
        for filename in ('load.py', 'postgres.py'):
            with self.subTest(filename=filename):
                text_patch, bytes_patch = self._change_source(filename, '\n# changed validator\n')
                with text_patch, bytes_patch:
                    self.assertEqual(history_contract.build_contract_sha256(), build_baseline)
                    self.assertNotEqual(history_contract.validator_contract_sha256(), validator_baseline)

    def test_unrelated_migration_is_outside_both_contracts(self):
        build_baseline = history_contract.build_contract_sha256()
        validator_baseline = history_contract.validator_contract_sha256()
        text_patch, bytes_patch = self._change_source('V4__index_similar_package.sql', '\n-- unrelated\n')
        with text_patch, bytes_patch:
            self.assertEqual(history_contract.build_contract_sha256(), build_baseline)
            self.assertEqual(history_contract.validator_contract_sha256(), validator_baseline)


if __name__ == '__main__':
    import unittest

    unittest.main()
