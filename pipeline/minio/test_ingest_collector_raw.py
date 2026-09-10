import unittest

from ingest_collector_raw import DATED_RUN, keywords_done, registry_done


class CompletenessTests(unittest.TestCase):
    def test_keywords_all_pages_fetched(self):
        done, _ = keywords_done({'pages_planned': 1000, 'pages_done': 1000})
        self.assertTrue(done)

    def test_keywords_partial_run_rejected(self):
        done, detail = keywords_done({'pages_planned': 1000, 'pages_done': 812})
        self.assertFalse(done)
        self.assertIn('812', detail)

    def test_registry_no_pending_tasks(self):
        done, _ = registry_done({'tasks_by_status': {'done': 99992, 'not_found': 4}})
        self.assertTrue(done)

    def test_registry_pending_tasks_rejected(self):
        done, _ = registry_done({'tasks_by_status': {'done': 8996, 'pending': 90996}})
        self.assertFalse(done)

    def test_manifest_without_progress_fields_rejected(self):
        # A manifest shape we do not recognise must not read as complete.
        self.assertFalse(keywords_done({})[0])
        self.assertFalse(registry_done({})[0])


class RunSelectionTests(unittest.TestCase):
    def test_dated_run_selected(self):
        self.assertTrue(DATED_RUN.fullmatch('run=2026-09-08'))

    def test_smoke_run_not_swept(self):
        self.assertIsNone(DATED_RUN.fullmatch('run=smoke-2026-09-08'))


if __name__ == '__main__':
    unittest.main()
