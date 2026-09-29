"""Standard test entry point for preprocessing tests."""
import argparse
import unittest
from pathlib import Path
from pipeline.preprocessing.common.paths import REPO_ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="list discovered tests")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern="test*.py", top_level_dir=str(REPO_ROOT))
    if args.list:
        for case in suite:
            for test in _flatten(case):
                print(test.id())
        if unittest.defaultTestLoader.errors:
            for error in unittest.defaultTestLoader.errors:
                print(error)
            return 1
        return 0
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


if __name__ == "__main__":
    raise SystemExit(main())
