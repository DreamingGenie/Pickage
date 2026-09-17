import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.preprocessing.requirements_resolution.input import file_sha256
from pipeline.preprocessing.requirements_resolution.policy import sha256
from pipeline.postgresql.version_dependents.historical_db_partition_probe import run


class PartitionInputBoundaryTests(unittest.TestCase):
    def test_metadata_and_payload_replacement_rejected_before_database_access(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'input';source.mkdir()
            payload=source/'counts.tsv';payload.write_bytes(b'original\n')
            metadata=source/'metadata.json'
            def rewrite():
                manifest={'files':[{'sha256':file_sha256(payload)}]}
                metadata.write_text(json.dumps({'manifest':manifest,'manifest_sha256':sha256(manifest)}))
            rewrite();pinned=file_sha256(metadata)
            payload.write_bytes(b'replacement\n');rewrite()
            with patch('pipeline.postgresql.version_dependents.historical_db_partition_probe.PgLoader') as database:
                with self.assertRaisesRegex(ValueError,'independently pinned'):
                    run(Path(folder)/'output',source,pinned)
                database.assert_not_called()

    def test_invalid_manifest_rejected_even_with_matching_metadata_file_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'input';source.mkdir()
            metadata=source/'metadata.json'
            metadata.write_text(json.dumps({'manifest':{'files':[]},'manifest_sha256':'0'*64}))
            with patch('pipeline.postgresql.version_dependents.historical_db_partition_probe.PgLoader') as database:
                with self.assertRaisesRegex(ValueError,'manifest hash'):
                    run(Path(folder)/'output',source,file_sha256(metadata))
                database.assert_not_called()


if __name__=='__main__':unittest.main()
