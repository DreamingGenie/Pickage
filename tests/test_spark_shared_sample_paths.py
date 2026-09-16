import unittest

from pipeline.spark_experiment.runtime.benchmark_data_phase import shared_input_key


class SharedSamplePathsTests(unittest.TestCase):
    def test_date_partition_survives_content_addressed_upload(self):
        key = shared_input_key({'path': '/sample/daily/date=2026-08-25/data.parquet', 'sha256': 'a' * 64})
        self.assertTrue(key.endswith('/date=2026-08-25/' + 'a' * 64 + '.parquet'))

    def test_non_partition_file_keeps_extension(self):
        self.assertTrue(shared_input_key({'path': '/sample/targets.csv', 'sha256': 'b' * 64})
                        .endswith('/' + 'b' * 64 + '.csv'))


if __name__ == '__main__':
    unittest.main()
