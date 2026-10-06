import unittest

from ingest_collector_raw import (DATED_RUN, SHARD_RUN, keywords_done, registry_done,
                                  shard_of, shard_total)


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


class ShardRunTests(unittest.TestCase):
    """4분할 수집(S15P21A506-366)은 run=<date>-s1 … -sN 네 폴더가 한 수집이다.
    묶는 기준과 완결 판정이 여기서 틀리면 원본의 일부만 올라간 채 _SUCCESS 가 찍힌다."""

    def test_shard_runs_share_one_collected_date(self):
        self.assertEqual(shard_of('run=2026-09-16-s1'), ('2026-09-16', 1))
        self.assertEqual(shard_of('run=2026-09-16-s4'), ('2026-09-16', 4))
        # 넷이 같은 날짜로 묶여야 collected_date 한 자리에 들어간다
        dates = {shard_of(f'run=2026-09-16-s{i}')[0] for i in range(1, 5)}
        self.assertEqual(dates, {'2026-09-16'})

    def test_unsharded_run_keeps_its_date_and_no_shard(self):
        self.assertEqual(shard_of('run=2026-09-09'), ('2026-09-09', None))

    def test_shard_run_is_swept(self):
        """예전에는 DATED_RUN 만 봐서 샤드 폴더가 하나도 선택되지 않았다."""
        self.assertIsNone(DATED_RUN.fullmatch('run=2026-09-16-s1'))
        self.assertTrue(SHARD_RUN.fullmatch('run=2026-09-16-s1'))

    def test_labelled_shard_run_is_swept(self):
        """회차 이름에 라벨이 붙어도 선택되고 날짜로 묶인다 (run=2026-09-22-additions-s1).
        라벨을 허용하기 전에는 네 폴더가 DATED_RUN·SHARD_RUN 어느 쪽에도 안 걸려 통째로 빠졌고,
        입고가 'No collector runs selected' 로 끝났다 (S15P21A506-452)."""
        self.assertTrue(SHARD_RUN.fullmatch('run=2026-09-22-additions-s1'))
        self.assertEqual(shard_of('run=2026-09-22-additions-s1'), ('2026-09-22', 1))
        # 라벨이 있어도 넷이 한 collected_date 로 묶여야 한다
        dates = {shard_of(f'run=2026-09-22-additions-s{i}')[0] for i in range(1, 5)}
        self.assertEqual(dates, {'2026-09-22'})
        # 라벨을 넓혀도 smoke 는 여전히 제외다
        self.assertIsNone(SHARD_RUN.fullmatch('run=smoke-2026-09-22-additions-s1'))

    def test_smoke_shard_not_swept(self):
        self.assertIsNone(SHARD_RUN.fullmatch('run=smoke-2026-09-16-s1'))
        self.assertIsNone(DATED_RUN.fullmatch('run=smoke-2026-09-16-s1'))

    def test_shard_total_comes_from_targets_name(self):
        """폴더 개수로 세면 s3 를 빠뜨린 채 올려도 통과한다. 대상 CSV 이름이 전체 수를 말한다."""
        # 수집기가 적는 targets 는 윈도 절대 경로다 (역슬래시 구분자)
        self.assertEqual(shard_total({'targets': 'C:\\git\\S15P21A506\\data\\registry\\targets\\rank_top100k_20260902-s1of4.csv'}), 4)
        self.assertEqual(shard_total({'targets': 'data/registry/targets/rank-s2of4.csv'}), 4)

    def test_shard_total_unknown_for_unsharded_targets(self):
        self.assertIsNone(shard_total({'targets': 'datasets/targets/rank_top100k_20260902.csv'}))
        self.assertIsNone(shard_total({}))

    def test_registry_shard_manifest_counts_only_its_own_slice(self):
        """샤드 manifest 의 pending 0 은 '이 샤드가 끝났다' 이지 '10만이 끝났다' 가 아니다.
        그래서 완결 판정은 샤드별 pending 과 샤드 수 둘 다 봐야 한다."""
        done, detail = registry_done({'tasks_by_status': {'done': 24812, 'not_found': 88,
                                                          'unpublished': 99}})
        self.assertTrue(done)
        self.assertIn('24812', detail)


if __name__ == '__main__':
    unittest.main()
