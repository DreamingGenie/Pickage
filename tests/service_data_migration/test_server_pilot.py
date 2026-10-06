import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

path = Path(__file__).parents[2] / 'scripts/service-data-migration/server_pilot.py'
spec = importlib.util.spec_from_file_location('server_pilot', path)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class PilotCsvTests(unittest.TestCase):
    def test_full_restore_has_separate_bundle_contract_and_no_archive_cap(self):
        self.assertEqual(pilot.restore_scope(full_restore=True, benchmark=False), '341-full-server-restore')
        self.assertIsNone(pilot.archive_size_limit(full_restore=True, benchmark=False))

    def test_existing_modes_keep_their_archive_contracts(self):
        self.assertEqual(pilot.restore_scope(full_restore=False, benchmark=True), '341-large-server-benchmark')
        self.assertEqual(pilot.archive_size_limit(full_restore=False, benchmark=True), 2 * 1024**3)
        self.assertEqual(pilot.restore_scope(full_restore=False, benchmark=False), '341-small-server-pilot')
        self.assertEqual(pilot.archive_size_limit(full_restore=False, benchmark=False), 20 * 1024**2)

    def test_monitor_is_bounded_and_slow_enough_for_long_runs(self):
        self.assertEqual(pilot.MONITOR_INTERVAL_SECONDS, 5.0)
        self.assertGreater(pilot.MAX_MONITOR_SAMPLES, 0)

    def test_full_bundle_requires_and_preserves_user_deferral_marker(self):
        marker, reason = pilot.full_source_validation_contract({
            'source_validation': 'DEFERRED_BY_USER',
            'source_validation_reason': '사용자가 원본 전수 검증을 유예함',
        })
        self.assertEqual(marker, 'DEFERRED_BY_USER')
        self.assertEqual(reason, '사용자가 원본 전수 검증을 유예함')
        with self.assertRaises(ValueError):
            pilot.full_source_validation_contract({'source_validation': 'DEFERRED'})

    def test_full_restore_stages_skip_all_value_and_signature_checks(self):
        phase = Mock(side_effect=lambda name, action: action())
        restore = Mock()
        flyway = Mock()
        validate_structure = Mock()
        analyze_candidate = Mock()

        with patch.object(pilot, 'signature_query', side_effect=AssertionError('full restore must not build signature SQL')):
            result = pilot.run_full_restore_stages(
                phase=phase,
                restore=restore,
                flyway=flyway,
                validate_structure=validate_structure,
                analyze_candidate=analyze_candidate,
                source_validation_reason='사용자 요청으로 원본 전수 검증을 유예함',
            )

        self.assertEqual(result['status'], 'RESTORED_UNVERIFIED')
        self.assertFalse(result['ready_for_service'])
        self.assertEqual(result['source_validation'], 'DEFERRED_BY_USER')
        self.assertTrue(result['source_validation_deferred'])
        self.assertEqual(phase.call_args_list[0].args[0], 'restore_full_archive')
        self.assertEqual(
            [entry.args[0] for entry in phase.call_args_list],
            ['restore_full_archive', 'flyway_v2_to_v6', 'flyway_validate',
             'validate_partition_structure', 'defer_source_validation', 'analyze_candidate'],
        )
        restore.assert_called_once_with()
        flyway.assert_any_call('migrate', 'latest')
        flyway.assert_any_call('validate', 'latest')
        validate_structure.assert_called_once_with()
        analyze_candidate.assert_called_once_with()

    def test_signature_query_is_bounded_to_known_tables(self):
        query = pilot.signature_query('package_version_snapshot')
        self.assertIn('md5(row_to_json(t)::text)', query)
        self.assertIn('substr(h,1,16)', query)
        self.assertIn('substr(h,17,16)', query)
        with self.assertRaises(ValueError):
            pilot.signature_query('package; DROP TABLE package')

    def test_row_order_can_differ_without_changing_values(self):
        prefix = b'package_id,version,description\n'
        a = b'1,1.0.0,"two\nlines"\n'
        b = b'1,1.0.0-rc.1,hello\n'
        self.assertEqual(pilot.csv_rows_by_key(prefix+a+b,'version'), pilot.csv_rows_by_key(prefix+b+a,'version'))

    def test_null_and_empty_string_remain_different(self):
        prefix = b'package_id,version,description\n'
        self.assertNotEqual(pilot.csv_rows_by_key(prefix+b'1,1.0.0,\n','version'),
                            pilot.csv_rows_by_key(prefix+b'1,1.0.0,""\n','version'))

    def test_changed_values_and_duplicate_keys_are_detected(self):
        prefix = b'package_id,version,snapshot_at,dependents_count\n'
        a = b'1,1.0.0,2026-08-31,7\n'
        b = b'1,1.0.0,2026-08-31,8\n'
        self.assertNotEqual(pilot.csv_rows_by_key(prefix+a,'package_version_snapshot'),
                            pilot.csv_rows_by_key(prefix+b,'package_version_snapshot'))
        with self.assertRaises(ValueError):
            pilot.csv_rows_by_key(prefix+a+a,'package_version_snapshot')


if __name__ == '__main__':
    unittest.main()
