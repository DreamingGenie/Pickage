import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector.storage import MetadataRepository


class QuotaAdmissionTests(unittest.TestCase):
    def test_concurrent_recovery_claims_each_expired_lease_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "collector.sqlite3"
            setup = MetadataRepository(root=tmpdir, db_path=db_path)
            setup.reserve_quota(
                "shared-subway", "2026-08-25", 3, 10, lease_seconds=1
            )
            setup.close()

            future = datetime.now(timezone.utc) + timedelta(seconds=2)
            barrier = threading.Barrier(2)
            results: list[int] = []
            errors: list[Exception] = []

            def recover() -> None:
                repository = MetadataRepository(root=tmpdir, db_path=db_path)
                try:
                    barrier.wait(timeout=5)
                    results.append(repository.recover_expired_quota(future))
                except Exception as exc:  # surfaced by assertions below
                    errors.append(exc)
                finally:
                    repository.close()

            threads = [threading.Thread(target=recover) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
            self.assertEqual(sorted(results), [0, 1])
            check = MetadataRepository(root=tmpdir, db_path=db_path)
            try:
                self.assertEqual(
                    check.quota_state("shared-subway", "2026-08-25", 10)["reserved"],
                    0,
                )
            finally:
                check.close()

    def test_reservations_prevent_shared_pool_overcommit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "collector.sqlite3"
            first = MetadataRepository(root=tmpdir, db_path=db_path)
            second = MetadataRepository(root=tmpdir, db_path=db_path)
            try:
                first.reserve_quota("shared-subway", "2026-08-25", 600, 1000)
                with self.assertRaises(ValueError):
                    second.reserve_quota("shared-subway", "2026-08-25", 500, 1000)
                first.consume_quota("shared-subway", "2026-08-25", 100)
                first.release_quota("shared-subway", "2026-08-25", 500)
                second.reserve_quota("shared-subway", "2026-08-25", 900, 1000)
            finally:
                first.close()
                second.close()

    def test_expired_reservation_is_recovered_after_repository_restart(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "collector.sqlite3"
            created = MetadataRepository(root=tmpdir, db_path=db_path)
            reservation_id = created.reserve_quota(
                "shared-subway",
                "2026-08-25",
                3,
                10,
                run_id="run-interrupted",
                lease_seconds=1,
            )
            self.assertEqual(created.quota_state("shared-subway", "2026-08-25", 10)["reserved"], 3)
            created.close()

            restarted = MetadataRepository(root=tmpdir, db_path=db_path)
            try:
                future = datetime.now(timezone.utc) + timedelta(seconds=2)
                self.assertEqual(restarted.recover_expired_quota(future), 1)
                state = restarted.quota_state("shared-subway", "2026-08-25", 10)
                self.assertEqual(state["reserved"], 0)
                self.assertEqual(state["remaining"], 10)
                row = restarted.connection.execute(
                    "SELECT run_id, status, reserved_count FROM quota_reservation WHERE reservation_id=?",
                    (reservation_id,),
                ).fetchone()
                self.assertEqual(dict(row), {
                    "run_id": "run-interrupted",
                    "status": "EXPIRED",
                    "reserved_count": 0,
                })
                # Recovery is idempotent and the reclaimed quota can be reused.
                self.assertEqual(restarted.recover_expired_quota(future), 0)
                restarted.reserve_quota("shared-subway", "2026-08-25", 10, 10)
            finally:
                restarted.close()

    def test_reservation_identity_settles_only_the_named_lease(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = MetadataRepository(root=tmpdir)
            try:
                first = repository.reserve_quota(
                    "shared-subway", "2026-08-25", 2, 10, run_id="run-a"
                )
                second = repository.reserve_quota(
                    "shared-subway", "2026-08-25", 2, 10, run_id="run-b"
                )
                repository.consume_quota("shared-subway", "2026-08-25", 1, first)
                rows = repository.connection.execute(
                    "SELECT reservation_id, reserved_count, status FROM quota_reservation ORDER BY reservation_id"
                ).fetchall()
                by_id = {row["reservation_id"]: dict(row) for row in rows}
                self.assertEqual(by_id[first]["reserved_count"], 1)
                self.assertEqual(by_id[first]["status"], "ACTIVE")
                self.assertEqual(by_id[second]["reserved_count"], 2)
                repository.release_quota("shared-subway", "2026-08-25", 1, first)
                self.assertEqual(repository.quota_state("shared-subway", "2026-08-25", 10)["reserved"], 2)
            finally:
                repository.close()


if __name__ == "__main__":
    unittest.main()
