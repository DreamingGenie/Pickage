import unittest

from .postgres import PgLoader


class PgLoaderSafetyTests(unittest.TestCase):
    def test_literal_escapes_sql(self):
        self.assertEqual(PgLoader._literal("x'; DROP TABLE package; --"), "'x''; DROP TABLE package; --'")

    def test_json_literal_is_json(self):
        self.assertEqual(PgLoader._literal({"x": "'"}), "'{\"x\":\"''\"}'")


if __name__ == "__main__":
    unittest.main()
