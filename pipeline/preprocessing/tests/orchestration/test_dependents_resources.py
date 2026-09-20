import unittest

from pipeline.preprocessing.orchestration.contracts import validate_request
from pipeline.preprocessing.tests.fixtures.orchestration_fixture import request_fixture
from pipeline.preprocessing.version_dependents.historical_parallel import _settings


class DependentsResourceTests(unittest.TestCase):
    def test_total_budget_is_split_between_cpu_workers(self):
        request = request_fixture()
        request["options"] = {"threads": 2, "memory_limit": "4GB", "workers": 8,
                              "dependents_workers": 2, "dependents_max_temp_size": "100GB"}
        self.assertEqual(validate_request(request), request)
        self.assertEqual(_settings(2, 2, "4GB", "100GB"),
                         {"threads": 1, "memory_limit": "2000MB", "max_temp_size": "50000MB"})

    def test_invalid_parallel_settings_fail_before_execution(self):
        for options in ({"dependents_workers": 3}, {"dependents_workers": True},
                        {"threads": 1, "dependents_workers": 2},
                        {"threads": 16}, {"dependents_max_temp_size": "unlimited"},
                        {"dependents_engine": "typo"}):
            with self.subTest(options=options):
                request = request_fixture()
                request["options"] = options
                with self.assertRaises(ValueError):
                    validate_request(request)

    def test_one_thread_can_use_one_worker(self):
        request = request_fixture()
        request["options"] = {"threads": 1}
        validate_request(request)


if __name__ == "__main__":
    unittest.main()
