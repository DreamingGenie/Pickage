import unittest

from pipeline.preprocessing.curated.repository import normalize_repository_url


class RepositoryUrlTests(unittest.TestCase):
    def test_malformed_authority_and_encoded_traversal_are_rejected(self):
        for value in ('https://[github.com/x/y', 'https://github.com/a/%252e%252e',
                      'https://github.com/a%2fb/c', 'https://github.com/a/repo:secret'):
            with self.subTest(value=value):
                self.assertIsNone(normalize_repository_url(value))
        self.assertEqual(normalize_repository_url('https://github.com/a/b.git/tree/main'),
                         'https://github.com/a/b')

    def test_normalizes_supported_transports(self):
        values = {
            "https://github.com/Facebook/react.git": "https://github.com/Facebook/react",
            "git+https://github.com/Facebook/react.git": "https://github.com/Facebook/react",
            "git://github.com/Facebook/react/": "https://github.com/Facebook/react",
            "ssh://git@github.com/Facebook/react.git": "https://github.com/Facebook/react",
            "git@github.com:Facebook/react.git": "https://github.com/Facebook/react",
            "https://gitlab.com/group/subgroup/project.git": "https://gitlab.com/group/subgroup/project",
            "git@gitlab.com:group/subgroup/project.git": "https://gitlab.com/group/subgroup/project",
            "github.com/Facebook/react": "https://github.com/Facebook/react",
            "github:Facebook/react": "https://github.com/Facebook/react",
        }
        for value, expected in values.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_repository_url(value), expected)

    def test_strips_query_fragment_and_known_ui_suffixes(self):
        self.assertEqual(
            normalize_repository_url("https://github.com/a/b/tree/main?x=1#readme"),
            "https://github.com/a/b",
        )
        self.assertEqual(
            normalize_repository_url("https://gitlab.com/a/b/-/tree/main"),
            "https://gitlab.com/a/b",
        )

    def test_rejects_untrusted_hosts_credentials_and_malformed_inputs(self):
        values = [
            None,
            "",
            "https://evil.com/a/b",
            "https://github.com.evil.com/a/b",
            "https://github.com:443/a/b",
            "https://user:secret@github.com/a/b",
            "https://admin@github.com/a/b",
            "https://github.com/a/../b",
            "https://github.com/a/%2e%2e/b",
            "https://github.com/a/%0A/b",
            "https://github.com/a/%3Ftoken=b/b",
            "https://github.com/a/%ZZ/b",
            "https://github.com/a/b/unknown-suffix",
            "https://gitlab.com/a/tree/main",
            "https://gitlab.com/a/b/tree/main",
            "https://gitlab.com/a/-/tree/main",
            "http://github.com/a/b?token=secret",  # query is stripped, not emitted
            "https://github.com/a",
            "ftp://github.com/a/b",
        ]
        for value in values[:-3]:
            with self.subTest(value=value):
                self.assertIsNone(normalize_repository_url(value))
        self.assertEqual(normalize_repository_url(values[-3]), "https://github.com/a/b")
        self.assertIsNone(normalize_repository_url(values[-2]))
        self.assertIsNone(normalize_repository_url(values[-1]))

    def test_rejects_overlong_result(self):
        path = "group/" + ("nested/" * 30) + "project"
        self.assertIsNone(normalize_repository_url("https://gitlab.com/" + path))


if __name__ == "__main__":
    unittest.main()
