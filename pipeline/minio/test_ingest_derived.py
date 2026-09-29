"""ingest_derived 의 계약 시험. 실제 S3 없이 순수 함수와 포인터 규칙만 본다.

여기 있는 것은 전부 "깨지면 조용히 틀리는" 것들이다 — 업로드 이름이 다른 파일에 사는
고정 인자와 어긋나거나, 이미 서버에 있는 실행의 manifest 바이트가 달라지거나,
포인터가 소비자를 옛 코퍼스로 되돌리는 경우다. 업로드·GET 검증 루프는 여기서 보지 않는다.
fake 로 감싸면 "boto3 를 불렀다" 만 확인하게 되고, 그건 MinIO 가 실패해도 통과한다.
"""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from botocore.exceptions import ClientError

from ingest_derived import (DATASETS, build_manifest, manifest_bytes, object_names,
                            pointer_value, publish_pointer, run_prefix, select_files)

PACKAGE_TEXT = DATASETS['package-text']
DEPRECATED = DATASETS['deprecated-replacement']


class FakeS3:
    """조건부 PUT 을 표현하는 최소 fake.

    pipeline/preprocessing/tests/curated/test_storage.py 에 같은 역할의 것이 있지만 그 파일은 flat import 라
    이 스위트에서 불러올 수 없다. CAS 에 필요한 두 메서드만 둔다.
    """

    def __init__(self, objects=None):
        self.objects = dict(objects or {})

    @staticmethod
    def _etag(body):
        return hashlib.md5(body).hexdigest()

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
        body = self.objects[Key]
        return {'Body': io.BytesIO(body), 'ETag': f'"{self._etag(body)}"'}

    def put_object(self, Bucket, Key, Body, IfMatch=None, IfNoneMatch=None):
        present = Key in self.objects
        if IfNoneMatch == '*' and present:
            raise ClientError({'Error': {'Code': 'PreconditionFailed'}}, 'PutObject')
        if IfMatch is not None and (not present
                                    or self._etag(self.objects[Key]) != IfMatch.strip('"')):
            raise ClientError({'Error': {'Code': 'PreconditionFailed'}}, 'PutObject')
        self.objects[Key] = Body
        return {'ETag': f'"{self._etag(Body)}"'}


class RunLayout(unittest.TestCase):
    def test_prefix_uses_the_datasets_own_partition_key(self):
        """깨지면: 객체가 소비자가 보는 경로와 다른 곳에 올라간다. deps.dev 쪽이 함께
        깨졌다면 이미 서버에 있는 snapshot= 경로가 움직였다는 뜻이다."""
        self.assertEqual(
            run_prefix(PACKAGE_TEXT, '2026-09-08', 'package-text-20260908-v1'),
            'ecosystems-keywords/v1/package-text'
            '/collected_date=2026-09-08/run_id=package-text-20260908-v1')
        self.assertEqual(
            run_prefix(DEPRECATED, '2026-08-31', 'deprecated-replacement-20260914-v1'),
            'depsdev/v1/deprecated-replacement'
            '/snapshot=2026-08-31/run_id=deprecated-replacement-20260914-v1')

    def test_upload_name_is_the_batch_contract(self):
        """깨지면: ai-similarity 의 --package-text /work/in/package_text.parquet 이 파일을
        못 찾아 배치가 죽는다. 그 고정 인자는 다른 저장소 폴더(deploy/)에 있어서 여기서
        붙잡아 두지 않으면 이 파일만 보고는 알 수 없다."""
        local = Path('data/keywords/package_text/package_text_2026-09-08.parquet')
        self.assertEqual(object_names(PACKAGE_TEXT, [local]), {local: 'package_text.parquet'})

    def test_upload_name_keeps_local_name_when_not_fixed(self):
        local = Path('data/deprecated_replacement/deprecated_replacement_20260831.parquet')
        self.assertEqual(object_names(DEPRECATED, [local]),
                         {local: 'deprecated_replacement_20260831.parquet'})

    def test_fixed_name_refuses_more_than_one_file(self):
        """깨지면: 둘이 같은 이름으로 겹쳐 올라가 코퍼스 절반이 조용히 사라진다."""
        with self.assertRaises(ValueError):
            object_names(PACKAGE_TEXT, [Path('a.parquet'), Path('b.parquet')])

    def test_select_files_leaves_other_collection_dates_alone(self):
        """깨지면: 다음 수집일 parquet 이 한 실행에 섞여 manifest 의 행 수가 두 수집일의
        합이 된다. 파일이 둘이 되므로 고정 이름 검사에 먼저 걸리기도 한다."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'package_text_2026-09-08.parquet').touch()
            (root / 'package_text_2026-10-06.parquet').touch()
            (root / 'summary_2026-09-08.json').touch()
            picked = select_files(PACKAGE_TEXT, root, '2026-09-08')
        self.assertEqual([p.name for p in picked], ['package_text_2026-09-08.parquet'])

    def test_select_files_says_which_builder_to_run(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError) as caught:
                select_files(PACKAGE_TEXT, Path(folder), '2026-09-08')
        self.assertIn(PACKAGE_TEXT['builder'], str(caught.exception))


class ManifestBytes(unittest.TestCase):
    def test_serialization_is_unchanged_for_the_run_already_in_the_bucket(self):
        """깨지면: 서버의 deprecated-replacement-20260914-v1 이 다시는 재검증으로 통과하지
        못한다. put_once 는 바이트를 비교하므로 구분자·키 이름이 한 글자만 달라도 거부된다."""
        record = {'file': 'data/deprecated_replacement_20260831.parquet',
                  'bytes': 2839460, 'sha256': 'ab' * 32, 'rows': 28241}
        body = manifest_bytes(build_manifest(DEPRECATED, 'deprecated-replacement', '2026-08-31',
                                             'deprecated-replacement-20260914-v1',
                                             [record], 2839460, 28241))
        self.assertIn(b'"snapshot": "2026-08-31"', body)   # 키 이름과 기본 구분자(": ")
        self.assertNotIn(b'collected_date', body)          # 새 키가 딸려 들어가지 않았다
        self.assertNotIn(b'source_file', body)             # 개명하지 않은 실행에는 없다
        self.assertEqual(json.loads(body)['files'], [record])

    def test_package_text_manifest_names_its_own_partition(self):
        body = manifest_bytes(build_manifest(PACKAGE_TEXT, 'package-text', '2026-09-08',
                                             'package-text-20260908-v1', [], 86159593, 922322))
        self.assertEqual(json.loads(body)['collected_date'], '2026-09-08')

    def test_superseding_run_borrows_the_dataset_name_its_loader_expects(self):
        """깨지면: pipeline/dependent_transitions/load.py 의 check_manifest 가 이 회차를
        "manifest 의 dataset 이 다르다" 로 거부한다. 그쪽은 상수 하나와 대조하고, 그 상수는
        etl_dataset_current 의 PK 이기도 해서 대체 회차가 빌려 써야 하는 이름이다."""
        spec = DATASETS['dependent-transitions-exp460k']
        self.assertEqual(spec['dataset_name'], 'dependent-transitions')
        body = build_manifest(spec, 'dependent-transitions-exp460k', '2026-08-31',
                              'dependent-transitions-exp460k-20260922-v1', [], 18922201, 4216671)
        self.assertEqual(body['dataset'], 'dependent-transitions')

    def test_a_dataset_without_the_override_keeps_its_own_key(self):
        """깨지면: dataset_name 기본값이 새어 다른 데이터셋의 manifest 이름까지 바뀐다."""
        body = build_manifest(DEPRECATED, 'deprecated-replacement', '2026-08-31',
                              'deprecated-replacement-20260914-v1', [], 2839460, 28241)
        self.assertEqual(body['dataset'], 'deprecated-replacement')


class Pointer(unittest.TestCase):
    KEY = 'ecosystems-keywords/v1/package-text/_current.json'

    def value(self, date_value, run_id):
        return pointer_value(PACKAGE_TEXT, date_value, run_id, 'cd' * 32)

    def test_first_publish_creates_it(self):
        s3 = FakeS3()
        state = publish_pointer(s3, self.KEY, self.value('2026-09-08', 'package-text-20260908-v1'),
                                'collected_date')
        self.assertEqual(state, 'created')
        stored = json.loads(s3.objects[self.KEY])
        self.assertEqual(stored['run_path'],
                         'collected_date=2026-09-08/run_id=package-text-20260908-v1')
        self.assertEqual(stored['run_id'], 'package-text-20260908-v1')
        self.assertNotIn('/', stored['run_id'])   # 소비자 산출물 경로의 깊이가 여기 달려 있다

    def test_same_value_writes_nothing(self):
        """깨지면: 재검증만 하려고 같은 명령을 다시 돌렸는데 포인터가 매번 새로 써진다."""
        value = self.value('2026-09-08', 'package-text-20260908-v1')
        s3 = FakeS3()
        publish_pointer(s3, self.KEY, value, 'collected_date')
        before = s3.objects[self.KEY]
        self.assertEqual(publish_pointer(s3, self.KEY, value, 'collected_date'), 'unchanged')
        self.assertIs(s3.objects[self.KEY], before)

    def test_refuses_to_point_back_at_an_older_collection(self):
        """깨지면: 과거 실행을 재검증했을 뿐인데 다음 배치가 옛 코퍼스로 돌아간다."""
        s3 = FakeS3()
        publish_pointer(s3, self.KEY, self.value('2026-10-06', 'package-text-20261006-v1'),
                        'collected_date')
        with self.assertRaises(ValueError):
            publish_pointer(s3, self.KEY, self.value('2026-09-08', 'package-text-20260908-v1'),
                            'collected_date')
        self.assertEqual(json.loads(s3.objects[self.KEY])['collected_date'], '2026-10-06')

    def test_advances_to_a_newer_collection(self):
        s3 = FakeS3()
        publish_pointer(s3, self.KEY, self.value('2026-09-08', 'package-text-20260908-v1'),
                        'collected_date')
        state = publish_pointer(s3, self.KEY, self.value('2026-10-06', 'package-text-20261006-v1'),
                                'collected_date')
        self.assertEqual(state, 'advanced')
        self.assertEqual(json.loads(s3.objects[self.KEY])['collected_date'], '2026-10-06')

    def test_repeated_put_failure_surfaces_the_real_error(self):
        """깨지면: 권한 오류가 동시성 충돌로 둔갑해, 운영자가 있지도 않은 동시 게시자를
        찾는다. 첫 실패는 경합일 수 있어 다시 읽어 보지만 두 번째는 원인을 올려야 한다."""
        class Denying(FakeS3):
            def put_object(self, **kwargs):
                raise ClientError({'Error': {'Code': 'AccessDenied'}}, 'PutObject')

        with self.assertRaises(ClientError):
            publish_pointer(Denying(), self.KEY,
                            self.value('2026-09-08', 'package-text-20260908-v1'),
                            'collected_date')

    def test_same_date_new_run_id_advances(self):
        """잘못 올린 회차를 고칠 길은 남겨 둔다 — 같은 수집일의 새 run 은 막지 않는다."""
        s3 = FakeS3()
        publish_pointer(s3, self.KEY, self.value('2026-09-08', 'package-text-20260908-v1'),
                        'collected_date')
        state = publish_pointer(s3, self.KEY, self.value('2026-09-08', 'package-text-20260908-v2'),
                                'collected_date')
        self.assertEqual(state, 'advanced')


if __name__ == '__main__':
    unittest.main()
