"""Compare the actual bounded validator with the previous SQL contract."""
import itertools
import unittest
import duckdb
from unittest.mock import patch
from pipeline.preprocessing.version_dependents.historical_parallel_input import _verify_source_consistency


class SourceConsistencyTests(unittest.TestCase):
    def test_all_nullable_flag_and_birth_pairs_match_original(self):
        with duckdb.connect() as con:
            con.execute('CREATE TABLE declarations(source_package_id INTEGER, source_version VARCHAR, birth_index INTEGER, dependency_error BOOLEAN)')
            states = list(itertools.product([None, 0, 1], [None, False, True]))
            for left, right in itertools.product(states, repeat=2):
                with self.subTest(left=left, right=right):
                    con.execute('DELETE FROM declarations')
                    con.executemany('INSERT INTO declarations VALUES (?,?,?,?)', [
                        (1, '1.0', *left), (1, '1.0', *right), (1, '1.0', *right),
                        (1, '2.0', 4, True), (2, '1.0', 9, False)])
                    conflict = con.execute("""SELECT EXISTS(SELECT 1 FROM declarations
                        GROUP BY source_package_id,source_version HAVING count(DISTINCT birth_index)>1
                        OR count(DISTINCT coalesce(dependency_error::VARCHAR,'NULL'))>1)""").fetchone()[0]
                    if conflict:
                        with self.assertRaisesRegex(ValueError, '^Source birth or error flag differs across shards$'):
                            _verify_source_consistency(con)
                    else:
                        _verify_source_consistency(con)

    def test_empty_input_is_accepted(self):
        with duckdb.connect() as con:
            con.execute('CREATE TABLE declarations(source_package_id INTEGER, source_version VARCHAR, birth_index INTEGER, dependency_error BOOLEAN)')
            _verify_source_consistency(con)

    def test_partitioned_validation_rejects_flags_across_forced_buckets(self):
        with duckdb.connect() as con:
            con.execute('CREATE TABLE declarations(source_package_id INTEGER, source_version VARCHAR, birth_index INTEGER, dependency_error BOOLEAN)')
            con.executemany('INSERT INTO declarations VALUES (?,?,?,?)', [
                (1, '1.0', 0, False), (2, '1.0', 0, False),
                (1, '1.0', 1, False)])
            with patch('pipeline.preprocessing.version_dependents.historical_parallel_input._VALIDATION_BUCKET_TARGET_ROWS', 1):
                with self.assertRaisesRegex(ValueError, 'Source birth or error flag differs'):
                    _verify_source_consistency(con)

if __name__ == '__main__':
    unittest.main()
