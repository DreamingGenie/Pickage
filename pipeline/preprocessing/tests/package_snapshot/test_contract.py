"""Contract hash scope tests for the package-snapshot loader."""

from __future__ import annotations

from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from pipeline.postgresql.package_snapshot import load


class PackageSnapshotContractHashTests(TestCase):
    def test_adding_unrelated_migration_does_not_change_hash(self):
        # Simulate a newly added V5 without creating any file in the checkout.
        migration_dir = load.ROOT / 'backend/src/main/resources/db/migration'
        future = migration_dir / 'V5__unrelated_feature.sql'
        original_glob = Path.glob
        original_read_text = Path.read_text
        baseline = load.contract_sha256()

        def with_future_file(path, pattern, *args, **kwargs):
            files = list(original_glob(path, pattern, *args, **kwargs))
            return iter(files + [future]) if path == migration_dir and pattern == 'V*.sql' else iter(files)

        def read_with_future(path, *args, **kwargs):
            if path == future:
                return 'CREATE TABLE unrelated_feature (id bigint PRIMARY KEY);'
            return original_read_text(path, *args, **kwargs)

        with patch.object(Path, 'glob', new=with_future_file), patch.object(Path, 'read_text', new=read_with_future):
            self.assertEqual(load.contract_sha256(), baseline)

    def test_unrelated_migration_content_does_not_change_hash(self):
        original_read_text = Path.read_text

        def with_unrelated_change(path, *args, **kwargs):
            content = original_read_text(path, *args, **kwargs)
            if path.name in {"V4__index_similar_package.sql", "V5__unrelated_feature.sql"}:
                return content + "\n-- temporary unrelated change\n"
            return content

        baseline = load.contract_sha256()
        with patch.object(Path, "read_text", new=with_unrelated_change):
            self.assertEqual(load.contract_sha256(), baseline)

    def test_related_migration_content_changes_hash(self):
        original_read_text = Path.read_text

        def with_related_change(path, *args, **kwargs):
            content = original_read_text(path, *args, **kwargs)
            if path.name == "V3__add_snapshot_reference_execution.sql":
                return content + "\n-- temporary related schema change\n"
            return content

        baseline = load.contract_sha256()
        with patch.object(Path, "read_text", new=with_related_change):
            self.assertNotEqual(load.contract_sha256(), baseline)


if __name__ == "__main__":
    import unittest

    unittest.main()
