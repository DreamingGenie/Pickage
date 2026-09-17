"""watch.py 의 순수 로직 테스트. 네트워크도 DB 도 쓰지 않는다.

    python -m pytest pipeline/similar_package/test_watch.py -v

여기서 보는 것은 "언제 부르는가" 하나다 — 게시 자체는 load.py 의 몫이고
이 파일은 load.py 를 절대 부르지 않는다 (부르려 하면 실패하도록 막아 둔다).
"""
import argparse
import datetime as dt
import json
import unittest
from unittest.mock import patch

from .watch import (
    in_window, latest_run, needs_publish, published, publish, tick, POINTER_KEY,
)
from .load import RESULT_BUCKET


RUN = "model=v3/corpus=package-text-20260914-v1"
OLDER = "model=v3/corpus=package-text-20260901-v1"
SHA = "a" * 64


class FakeBody:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload


class FakeS3:
    """포인터 객체 하나만 흉내 낸다. 없으면 실제 boto3 처럼 예외를 던진다."""

    def __init__(self, pointer=None, runs=()):
        self.pointer = pointer
        self.runs = list(runs)
        self.gets = []

    def get_object(self, Bucket, Key):
        self.gets.append((Bucket, Key))
        if self.pointer is None:
            raise RuntimeError("NoSuchKey")
        return {"Body": FakeBody(json.dumps(self.pointer).encode())}


def make_args(**overrides):
    values = dict(database="pickage", db_user="postgres", docker_container=None,
                  psql="psql", allow_gate_skip=False, verify_only=False,
                  window=None, dry_run=False)
    values.update(overrides)
    return argparse.Namespace(**values)


class WindowTests(unittest.TestCase):
    def test_no_window_always_allows(self):
        self.assertTrue(in_window(None, dt.time(3, 0)))
        self.assertTrue(in_window("", dt.time(15, 0)))

    def test_plain_window(self):
        self.assertTrue(in_window("02:00-06:00", dt.time(3, 0)))
        self.assertTrue(in_window("02:00-06:00", dt.time(2, 0)))
        self.assertFalse(in_window("02:00-06:00", dt.time(6, 0)))  # 끝은 열려 있다
        self.assertFalse(in_window("02:00-06:00", dt.time(7, 0)))

    def test_window_crossing_midnight(self):
        self.assertTrue(in_window("22:00-04:00", dt.time(23, 0)))
        self.assertTrue(in_window("22:00-04:00", dt.time(3, 0)))
        self.assertFalse(in_window("22:00-04:00", dt.time(12, 0)))

    def test_bad_format_stops(self):
        with self.assertRaises(SystemExit):
            in_window("2시-6시")


class NeedsPublishTests(unittest.TestCase):
    def test_same_hash_is_already_published(self):
        self.assertIsNone(needs_publish(RUN, SHA, RUN, SHA))

    def test_different_hash_needs_publish(self):
        self.assertIsNotNone(needs_publish(RUN, SHA, OLDER, "b" * 64))

    def test_same_path_with_new_content_needs_publish(self):
        # 해시가 양쪽에 있으면 경로가 같아도 내용이 바뀐 것을 잡는다
        self.assertIsNotNone(needs_publish(RUN, SHA, RUN, "b" * 64))

    def test_falls_back_to_path_when_hash_missing(self):
        self.assertIsNone(needs_publish(RUN, "", RUN, ""))
        self.assertIsNotNone(needs_publish(RUN, "", OLDER, ""))

    def test_empty_database_needs_publish(self):
        self.assertIsNotNone(needs_publish(RUN, SHA, "", ""))


class LatestRunTests(unittest.TestCase):
    def test_reads_pointer(self):
        s3 = FakeS3({"run_path": RUN, "manifest_sha256": SHA})
        self.assertEqual(latest_run(s3), (RUN, SHA))
        self.assertEqual(s3.gets, [(RESULT_BUCKET, POINTER_KEY)])

    def test_pointer_without_hash(self):
        self.assertEqual(latest_run(FakeS3({"run_path": RUN})), (RUN, ""))

    def test_rejects_malformed_run_path(self):
        with self.assertRaises(SystemExit):
            latest_run(FakeS3({"run_path": "../etc/passwd"}))

    def test_falls_back_to_listing_when_pointer_absent(self):
        with patch("pipeline.similar_package.watch.list_runs", return_value=[OLDER, RUN]):
            self.assertEqual(latest_run(FakeS3(None)), (RUN, ""))

    def test_nothing_to_publish(self):
        with patch("pipeline.similar_package.watch.list_runs", return_value=[]):
            self.assertIsNone(latest_run(FakeS3(None)))


class PublishedTests(unittest.TestCase):
    def run_with(self, returncode, stdout):
        class Done:
            pass
        done = Done()
        done.returncode, done.stdout, done.stderr = returncode, stdout, ""
        with patch("pipeline.similar_package.watch.subprocess.run", return_value=done):
            return published(["psql"])

    def test_parses_row(self):
        self.assertEqual(self.run_with(0, f"{RUN}|{SHA}\n"), (RUN, SHA))

    def test_empty_when_nothing_published(self):
        self.assertEqual(self.run_with(0, "\n"), ("", ""))

    def test_raises_on_psql_failure(self):
        with self.assertRaises(RuntimeError):
            self.run_with(2, "")


class TickTests(unittest.TestCase):
    def tick_with(self, pointer, db_row, args):
        class Done:
            returncode, stdout, stderr = 0, f"{db_row[0]}|{db_row[1]}\n", ""
        with patch("pipeline.similar_package.watch.subprocess.run", return_value=Done()), \
             patch("pipeline.similar_package.watch.publish") as called:
            called.return_value = True
            result = tick(FakeS3(pointer), ["psql"], args)
        return result, called

    def test_does_not_publish_when_unchanged(self):
        result, called = self.tick_with({"run_path": RUN, "manifest_sha256": SHA},
                                        (RUN, SHA), make_args())
        self.assertFalse(result)
        called.assert_not_called()

    def test_publishes_when_changed(self):
        result, called = self.tick_with({"run_path": RUN, "manifest_sha256": SHA},
                                        (OLDER, "b" * 64), make_args())
        self.assertTrue(result)
        self.assertEqual(called.call_args[0][0], RUN)

    def test_dry_run_never_publishes(self):
        _, called = self.tick_with({"run_path": RUN, "manifest_sha256": SHA},
                                   ("", ""), make_args(dry_run=True))
        called.assert_not_called()

    def test_outside_window_never_publishes(self):
        outside = (dt.datetime.now() + dt.timedelta(hours=6)).strftime("%H:%M")
        end = (dt.datetime.now() + dt.timedelta(hours=7)).strftime("%H:%M")
        _, called = self.tick_with({"run_path": RUN, "manifest_sha256": SHA},
                                   ("", ""), make_args(window=f"{outside}-{end}"))
        called.assert_not_called()


class PublishCommandTests(unittest.TestCase):
    def command_for(self, run, sha, args):
        class Done:
            returncode = 0
        with patch("pipeline.similar_package.watch.subprocess.run", return_value=Done()) as ran:
            publish(run, sha, args)
        return ran.call_args[0][0]

    def test_execution_id_is_deterministic(self):
        first = self.command_for(RUN, SHA, make_args())
        second = self.command_for(RUN, SHA, make_args())
        self.assertEqual(first, second)
        self.assertIn("--execution-id", first)

    def test_execution_id_changes_with_content(self):
        first = self.command_for(RUN, SHA, make_args())
        second = self.command_for(RUN, "b" * 64, make_args())
        index = first.index("--execution-id") + 1
        self.assertNotEqual(first[index], second[index])

    def test_passes_run_and_target(self):
        command = self.command_for(RUN, SHA, make_args())
        self.assertIn("pipeline.similar_package.load", command)
        self.assertEqual(command[command.index("--run") + 1], RUN)
        self.assertEqual(command[command.index("--psql") + 1], "psql")

    def test_docker_container_mode(self):
        command = self.command_for(RUN, SHA, make_args(docker_container="pg", psql=None))
        self.assertEqual(command[command.index("--docker-container") + 1], "pg")
        self.assertNotIn("--psql", command)

    def test_forwards_flags(self):
        command = self.command_for(RUN, SHA, make_args(allow_gate_skip=True, verify_only=True))
        self.assertIn("--allow-gate-skip", command)
        self.assertIn("--verify-only", command)


if __name__ == "__main__":
    unittest.main()
