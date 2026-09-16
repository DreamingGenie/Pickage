"""Upload derived Parquet datasets to pickage-curated; verify every object by GET SHA-256.

deps.dev snapshots go through ingest_raw.py and API collector runs through
ingest_collector_raw.py, both into pickage-raw. This one takes the smaller
datasets that a builder computes from those originals - pipeline/duckdb/build_*.py
and the collectors' own build_*.py. They belong next to the Curated
package/version output, not among the raw sources: re-running the builder
reproduces them, but only on a machine still holding the tens of gigabytes of
raw Parquet.

A dataset marked `pointer` also publishes `_current.json` at its prefix root,
naming the run that consumers should read. For package-text that file is what
makes the similarity batch run at all.

    python -m pipeline.minio.ingest_derived --dataset deprecated-replacement --dry-run
    python -m pipeline.minio.ingest_derived --dataset package-text --run-id package-text-20260908-v1
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import hashlib
import json
import re
import uuid

from boto3.s3.transfer import TransferConfig
import duckdb

# 포인터 게시에 필요한 조건부 PUT 은 Curated 쪽에 이미 있다 (put_once 는 ETag 를 돌려주지
# 않아 CAS 를 못 한다). 기반 계층이 상위 패키지를 부르는 모양이라 리뷰에서 볼 것 — 다만
# storage.py 는 pipeline.minio 를 import 하지 않으므로 순환은 아니다.
from pipeline.curated.storage import compare_and_swap_json, json_bytes, read_optional
from pipeline.minio.ingest_raw import ROOT, client, digest, exists, put_once


BUCKET = 'pickage-curated'

# A dataset says where its Parquet is built locally, where it goes in the bucket,
# and which git README explains the columns. `notes` carries what someone holding
# only the bucket could not work out - precision, what was deliberately left out.
#
#   partition    name of the date partition key. The raw ingesters already differ
#                (deps.dev has snapshot=, the API collectors have collected_date=)
#                and a derived set keeps the word its source uses.
#   date         default partition value; --date overrides it.
#   glob         picks this run's files only. '{date}' is filled in. Without it a
#                second collection date sitting in the same folder joins this run.
#   object_name  fixed name under data/. Only for a consumer that hardcodes it.
#   pointer      publish _current.json at the prefix root.
DATASETS = {
    'deprecated-replacement': {
        'root': 'data/deprecated_replacement',
        'prefix': 'depsdev/v1/deprecated-replacement',
        'partition': 'snapshot',
        'date': '2026-08-31',
        'builder': 'pipeline/duckdb/build_deprecated_dataset.py',
        'source': 'pickage-raw depsdev/v1 versions_full + pkg_project (snapshot=2026-08-31)',
        'readme': 'datasets/deprecated_replacement_260831/README.md',
        'jira': ['S15P21A506-272', 'S15P21A506-343'],
        'notes': [
            '폐기 문구에서 대체 패키지명을 정규식으로 뽑은 28,241행. 눈검사 기준 정밀도 85~90%,'
            ' replacement_confidence=high 만 쓰면 더 높다.',
            'replacement_repo_url 은 대체 패키지의 저장소 주소(24,868행). pkg_project 의'
            ' SOURCE_REPO_TYPE 매핑에서 만들었고, 매핑이 없는 334건은 원문 열만 있다.',
            '같은 내용의 CSV·JSONL 은 git datasets/deprecated_replacement_260831/ 에 있어 여기 올리지 않음.',
        ],
    },
    'migration-pairs-dev': {
        'root': 'data/migration_pairs_dev',
        # deps.dev 가 아니라 npm registry 수집분에서 나온 것이라 npm-registry/v1 아래에 둔다
        # (원본 수집분은 ingest_collector_raw.py 가 같은 접두사에 넣는다).
        'prefix': 'npm-registry/v1/migration-pairs-dev',
        # 이 데이터셋의 파티션 키는 snapshot= 이다. 값은 deps.dev 스냅샷이 아니라 원천이 된
        # registry 수집 실행 날짜이므로 아래 package-text 처럼 collected_date 여야 맞다. 그런데
        # migration-pairs-dev-20260914-v1 이 이미 snapshot= 으로 입고돼 있다 (S15P21A506-349).
        # 여기를 고치면 입고기가 없는 경로를 보게 되고 재실행이 같은 데이터를 한 벌 더 올린다.
        'partition': 'snapshot',
        'date': '2026-09-09',
        'builder': 'pipeline/duckdb/build_migration_pairs.py --source registry --kind dev',
        'source': 'pickage-raw npm-registry/v1 collected_date=2026-09-09 (의존 선언·발행시각) '
                  '+ depsdev/v1 versions_full snapshot=2026-08-31 (source_repo 만, publisher 판정용)',
        'readme': 'datasets/migration_pairs_dev_260914/README.md',
        'jira': ['S15P21A506-280', 'S15P21A506-349', 'S15P21A506-136'],
        'notes': [
            '개발용 의존(devDependencies) 기준 이동쌍. 실행용 의존 기준 결과는 같은 버킷의'
            ' depsdev/v1/migration-pairs/ 에 있다. 모집단이 달라(상위 10만 vs npm 전수)'
            ' 두 결과의 수치를 더하거나 lift 를 비교하면 안 된다.',
            '모집단은 다운로드 순위 상위 10만이다. 그 밖의 패키지가 도구를 어떻게 바꿨는지는 알 수 없다.',
            '제거 판정에서 같은 전이의 Dependencies·Peer·Optional 로 옮겨진 이름은 재분류로 보고 뺐다(27,732건).',
            '쌍 CSV 3종(strict 766·recommended 506·all 6,770)과 재분류 정정 측정 결과는'
            ' git datasets/migration_pairs_dev_260914/ 에 있어 여기 올리지 않음.',
        ],
    },
    'package-dependents': {
        'root': 'data/package_dependents',
        'prefix': 'depsdev/v1/package-dependents',
        'partition': 'snapshot',
        'date': '2026-08-31',
        'builder': 'pipeline/duckdb/build_package_dependents.py',
        'source': 'pickage-raw depsdev/v1 requirements + versions_full (snapshot=2026-08-31)'
                  ' + datasets/targets/rank_top100k_20260902.csv (대상 목록)',
        'readme': 'datasets/package_dependents_260915/README.md',
        'jira': ['S15P21A506-354', 'S15P21A506-173'],
        'notes': [
            '패키지별 dependents(의존자) 이름 목록. (name, kind) 1행 299,988 = 대상 99,996 ×'
            ' regular/peer/optional. 기존 dependents 데이터는 전부 수(count) 뿐이라'
            ' 교집합을 잴 수 없어서 목록으로 새로 냈다.',
            '대상은 다운로드 상위 10만이고 의존자는 npm 전수 4,065,913 이다. 그래서 대상 밖'
            ' 패키지의 dependents 는 알 수 없다 — 폐기→대체 정답지 25,601 쌍 중 양쪽 다'
            ' 데이터가 있는 것은 905 쌍(3.5%) 뿐이다.',
            '쓰는 쪽에서 교집합을 잴 때 분모는 min(|A|,|B|) 로 한다. Jaccard 로 재면'
            ' webpack↔webpack-cli 가 0.231 이라 보완재인데 0.3 관문을 통과해 버린다.',
            'devDependencies 는 원천(NPMRequirements)에 없다. typescript 가 57,189 로'
            ' ecosyste.ms 488,056 의 0.12 배다. eslint·jest·prettier 류 판단에 쓰면 안 된다.',
            '의존자 모집단에서 번들 중첩 의존 경로 노드를 뺐다. versions_full 고유 이름'
            ' 1,138만 중 705만(61.9%)이 `@winglang/sdk>0.76.19>cdktf>safe-buffer` 형태이고'
            ' 전부 published_at 이 NULL 이다. 빼지 않으면 tslib 이 116,820 대신 972,523 이 된다.',
            '직접 의존만이다. 2-hop 은 이 파일로 계산할 수 없다 — 의존자로 등장하는 고유'
            ' 패키지 2,157,744 중 이 표에 행이 있는 것은 64,706(3.0%) 뿐이다.',
            '정답지 이동쌍의 8~11% 가 0.3 관문에 걸린다(거짓 탈락). @types/X→X,'
            ' -compat/-shim→본체 가 주 패턴이므로 hard filter 가 아니라 감점으로 쓴다.',
            '배열을 뺀 요약 CSV·stats.json 은 git datasets/package_dependents_260915/ 에 있어'
            ' 여기 올리지 않음. 배열은 CSV 셀에 들어가지 않는다(react 한 행이 19만 원소).',
        ],
    },
    'package-dependents-candidate-pool': {
        # package-dependents 와 폴더·prefix 를 나눈다. 계산은 같고 **대상 모집단만 다른**
        # 회차라, 같은 prefix 에 run_id 로만 구분해 두면 받는 쪽이 어느 것이 무엇인지
        # 알 수 없다. 이 입고기는 root 의 *.parquet 를 통째로 올리기도 한다.
        'root': 'data/package_dependents_candidate_pool_260916',
        'prefix': 'depsdev/v1/package-dependents-candidate-pool',
        'partition': 'snapshot',
        'date': '2026-08-31',
        'builder': 'pipeline/duckdb/build_package_dependents.py'
                   ' --targets datasets/targets/candidate_pool_260916.csv'
                   ' --label candidate_pool_260916',
        'source': 'pickage-raw depsdev/v1 requirements + versions_full (snapshot=2026-08-31)'
                  ' + datasets/targets/candidate_pool_260916.csv (AI 파트 제공 후보 풀)',
        'readme': 'datasets/package_dependents_candidate_pool_260916/README.md',
        'jira': ['S15P21A506-359', 'S15P21A506-173'],
        'notes': [
            'AI 후보 풀 29,310 개를 대상으로 한 dependents 목록. (name, kind) 1행 87,930 ='
            ' 29,310 × regular/peer/optional. 열 구성은 같은 버킷의'
            ' depsdev/v1/package-dependents/ 와 **완전히 같고 대상 목록만 다르다.**',
            '이 회차를 따로 낸 이유는 후보 풀의 11,297 개(38.5%)가 다운로드 상위 10 만 밖이라'
            ' 기존 회차로는 답할 수 없었기 때문이다. 두 회차에 겹치는 54,039 행은 개수도'
            ' dependents 배열도 불일치 0 으로 확인했다 — 계산이 같으므로 같아야 하는 값이다.',
            '상위 10 만 밖 11,297 개는 download_rank·ecosystems_dependent_count 가 NULL 이다.'
            ' 값을 못 구한 것이 아니라 그 표에 없는 패키지라서이고, NULL 자체가 "순위 밖"이다.'
            ' 그중 9,655 개에 의존자가 있으나 엣지 합은 96,543 으로 이 회차 786 만의 1.2% 다.',
            '교집합을 잴 때 분모는 min(|A|,|B|) 로 한다. Jaccard 로 재면 webpack↔webpack-cli 가'
            ' 0.231 이라 보완재인데 0.3 관문을 통과해 버린다.',
            'devDependencies 는 원천(NPMRequirements)에 없다. 이 회차에서도 typescript 가'
            ' 57,189 로 ecosyste.ms 488,056 의 0.12 배다. 개발 도구 판단에 쓰면 안 된다.',
            '정답지 이동쌍의 8~11% 가 0.3 관문에 걸린다(거짓 탈락). hard filter 가 아니라'
            ' 감점으로 쓰고, 데이터가 없는 쌍은 탈락이 아니라 통과로 둔다.',
            '요약 CSV·stats·README 는 git datasets/package_dependents_candidate_pool_260916/ 에'
            ' 있어 여기 올리지 않는다. 배열은 CSV 셀에 들어가지 않는다(react 한 행이 19만 원소).',
        ],
    },
    'package-text': {
        'root': 'data/keywords/package_text',
        'prefix': 'ecosystems-keywords/v1/package-text',
        'partition': 'collected_date',
        'date': '2026-09-08',
        'glob': 'package_text_{date}.parquet',
        'object_name': 'package_text.parquet',
        'pointer': True,
        'builder': 'pipeline/collectors/keywords/build_package_text.py',
        'source': 'pickage-raw ecosystems-keywords/v1/collected_date=2026-09-08/'
                  'run_id=keywords-20260909-v1 + deps.dev versions_full Description',
        'readme': 'pipeline/collectors/keywords/README.md',
        'jira': ['S15P21A506-275', 'S15P21A506-348'],
        'notes': [
            '유사 패키지 모델의 임베딩 입력. 수집 1,000,000 행 → name 기준 중복 제거 999,801'
            ' → status removed·unpublished 제외 922,322 행.',
            '로컬 파일명은 package_text_<수집일>.parquet 이고 올릴 때만 package_text.parquet 으로'
            ' 바꾼다. ai-similarity 가 --package-text /work/in/package_text.parquet 으로 이름을'
            ' 고정해 받기 때문이다.',
            'keywords_source: npm 516,008 / github_topics 40,441 / none 365,873.'
            ' description_source: npm 840,467 / repo 10,568 / depsdev 10,062 / none 61,225.',
            'is_spam 23,589 행은 지우지 않고 표시만 했다. 거르는 것은 쓰는 쪽 몫이다 —'
            ' 학습에 쓸 때는 NOT is_spam AND description IS NOT NULL AND keywords_source <> \'none\'.',
            '원본 keywords 는 ecosyste.ms 이고 CC BY-SA 4.0 이다. 파생물을 발표·배포할 때 출처를 밝힌다.',
            '이 prefix 의 _current.json 이 이 실행을 가리키면 유사도 배치가 다음 회차에 이 코퍼스를 집는다.',
        ],
    },
    'peer-similarity': {
        'root': 'data/peer_similarity',
        # peer 값 자체는 deps.dev requirements 에서만 온다. 비교 대상 쌍 목록에 registry 기반
        # 개발용 이동쌍이 섞여 있지만, 열의 원천과 스냅샷 기준은 deps.dev 2026-08-31 이다.
        'prefix': 'depsdev/v1/peer-similarity',
        'partition': 'snapshot',
        'date': '2026-08-31',
        'pointer': True,
        'builder': 'pipeline/duckdb/build_peer_similarity.py',
        'source': 'pickage-raw depsdev/v1 requirements + versions_full (snapshot=2026-08-31). '
                  '비교 대상 쌍: datasets/migration_pairs_260908 · migration_pairs_dev_260914 · '
                  'deprecated_replacement_260831',
        'readme': 'datasets/peer_similarity_260914/README.md',
        'jira': ['S15P21A506-350', 'S15P21A506-110'],
        'notes': [
            '"A 가 B 를 대체할 수 있나" 판단용 peer 의존 유사도. package_peers 는 패키지 1행(최신 릴리스),'
            ' pair_peer_similarity 는 쌍 1행이며 양쪽 peer 목록·교집합·Jaccard·판정을 담는다.',
            'peer_verdict 의 no_peer_either(31,971행)는 결측이 아니라 범주다. peer 는 희소해서 쌍의'
            ' 60%가 양쪽 다 없다. peer_jaccard NULL 을 0 으로 채우면 모델이 결측을 "대체 불가" 로 배운다.',
            'hard filter 가 아니라 감점 입력이다. tslint→eslint 는 peer 겹침 0(typescript vs jiti)인데'
            ' 정답지에 있는 진짜 대체쌍이다. 불일치만으로 탈락시키면 이런 쌍을 잃는다.',
            '버전 기준은 최신 릴리스다. A 가 폐기·방치된 패키지면 그 최신은 몇 년 전 선언이라'
            ' 그 시절 생태계를 반영한다(moment 의 peer 는 2020년 기준). 이동 시점 기준은 별도 작업.',
            '같은 내용의 CSV 는 git datasets/peer_similarity_260914/ 에 있어 여기 올리지 않음.',
        ],
    },
    'package-peers': {
        # peer-similarity 와 폴더를 나눈다. 이 입고기는 root 의 *.parquet 를 통째로 올리므로
        # 한 폴더에 두면 이미 _SUCCESS 가 찍힌 실행에 파일이 늘어 재검증이 막힌다.
        'root': 'data/package_peers',
        'prefix': 'depsdev/v1/package-peers',
        'partition': 'snapshot',
        'date': '2026-08-31',
        'pointer': True,
        'builder': 'pipeline/duckdb/build_peer_similarity.py --scope all',
        'source': 'pickage-raw depsdev/v1 requirements + versions_full (snapshot=2026-08-31), '
                  'download_rank 은 datasets/targets/rank_top100k_20260902.csv',
        'readme': 'datasets/peer_similarity_260914/README.md',
        'jira': ['S15P21A506-350', 'S15P21A506-110'],
        'notes': [
            'npm 전수에서 peerDependencies 를 가진 패키지의 최신 릴리스 peer 목록. 쌍 목록과 무관하게'
            ' 임의의 두 패키지를 즉석에서 비교하기 위한 재료다. peer 가 없는 패키지(전체 406만 중'
            ' 80.0%)는 행 자체를 넣지 않는다 — 없다는 사실은 행이 없는 것으로 똑같이 표현된다.',
            'package_peers_all 814,025행 · package_peers_recent 531,830행(최신 릴리스 2023-01-01 이후).'
            ' recent 는 all 의 부분집합이고 열 구성이 같다.',
            '전수를 그대로 쓰지 말 것. all 의 23.9%가 릴리스 1개짜리이고 41.1%는 3년 넘게 방치돼 있다.'
            ' 다운로드 상위 10만 안에 드는 것은 29,193개(3.6%)뿐이다. 하한을 어디에 둘지는 용도마다'
            ' 달라서 n_releases·last_published_at·is_deprecated·download_rank 를 열로 함께 담았다.',
            '2026-09-15 정정 — 앞선 run_id=package-peers-20260915-v1 의 all 1,033,323행에는 실제'
            ' 패키지가 아닌 219,299행(21.2%)이 섞여 있었다. `@winglang/sdk>0.76.19>cdktf>safe-buffer`'
            ' 처럼 deps.dev 가 번들 중첩 의존 경로를 노드로 담은 것들이고 npm 이름에 `>` 는 쓸 수 없다.'
            ' 최신 릴리스 판정에 published_at IS NOT NULL 을 더해 걸러냈다(S15P21A506-283 과 같은 기준).'
            ' 그 run 은 쓰지 말 것.',
            '쌍 단위 비교 결과는 같은 버킷의 depsdev/v1/peer-similarity/ 에 있다. 그쪽은 대상 필터가'
            ' 이미 가짜 노드를 걸러 영향이 없었고 재계산해도 결과가 바이트까지 같았다.',
        ],
    },
}


def run_prefix(spec, date_value, run_id):
    """Bucket-relative path of one run. The partition key name differs per dataset."""
    return f'{spec["prefix"]}/{spec["partition"]}={date_value}/run_id={run_id}'


def select_files(spec, folder, date_value):
    """This run's Parquet only - a later collection date in the same folder is not ours."""
    pattern = spec.get('glob', '*.parquet').format(date=date_value)
    files = sorted(folder.glob(pattern))
    if not files:
        raise ValueError(f'No Parquet matching {pattern} under {spec["root"]}:'
                         f' run {spec["builder"]} first')
    return files


def object_names(spec, files):
    """Local path -> name under data/. Renaming is for a consumer that hardcodes it."""
    fixed = spec.get('object_name')
    if not fixed:
        return {path: path.name for path in files}
    if len(files) != 1:
        # Two files under one name would upload over each other, and the threads
        # would report it as 'Remote checksum mismatch' - which does not say why.
        raise ValueError(f'object_name expects exactly one file, found {len(files)}:'
                         f' {", ".join(p.name for p in files)}')
    return {files[0]: fixed}


def build_manifest(spec, dataset, date_value, run_id, records, size, row_total):
    """Manifest body. The date key is named after the dataset's own partition."""
    return {'contract_version': 1, 'run_id': run_id, 'status': 'PASSED',
            'dataset': dataset, spec['partition']: date_value,
            'file_count': len(records), 'bytes': size, 'row_count': row_total,
            'verification': 'GET_SHA256_ALL_FILES',
            'builder': spec['builder'], 'source': spec['source'],
            'readme': spec['readme'], 'jira': spec['jira'], 'notes': spec['notes'],
            'files': records}


def manifest_bytes(manifest):
    """Do not switch this to storage.json_bytes (compact separators). put_once compares
    bytes, so a different serializer makes every run already in the bucket fail to
    re-verify instead of passing."""
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()


def pointer_value(spec, date_value, run_id, manifest_sha):
    """_current.json body.

    run_path is relative to the dataset prefix because the consumer already holds
    that prefix in its own config (.env AI_CORPUS_PREFIX); carrying the whole path
    here would give the two copies a place to disagree. run_id stays flat - it is
    stamped into the consumer's output path, where an extra '/' would change the
    directory depth.
    """
    return {spec['partition']: date_value,
            'manifest_sha256': manifest_sha,
            'run_id': run_id,
            'run_path': f'{spec["partition"]}={date_value}/run_id={run_id}'}


def refuse_rollback(current, date_value, date_key, key):
    """Raise when the pointer already names a later collection than the one publishing.

    Re-verifying an older completed run is fine; sending the consumer back to that
    older corpus is not. Called twice per run - once before uploading, so a refusal
    costs nothing, and again inside publish_pointer, which is the decision that counts.
    """
    if not isinstance(current, dict):
        return                      # 없거나 알아볼 수 없는 포인터는 이 판정의 대상이 아니다
    seen = str(current.get(date_key, ''))
    if seen > date_value:
        raise ValueError(f'Current pointer is newer ({seen} > {date_value}):'
                         f' refusing to roll {key} back')


def publish_pointer(s3, key, value, date_key):
    """Move _current.json to this run, or refuse. Returns what it did.

    No writer lock: one person runs this by hand and no two of them publish the
    same dataset at once. A lock would only add one that someone has to clear after
    a hard stop.
    """
    for attempt in range(2):
        previous = read_optional(s3, BUCKET, key)
        current = json.loads(previous[0]) if previous else None
        if current == value:
            return 'unchanged'
        try:
            refuse_rollback(current, value[date_key], date_key, key)
        except ValueError as error:
            # 여기까지 왔으면 객체·manifest·_SUCCESS 는 이미 다 올라가 있다. 그 사실을
            # 말해 주지 않으면 "실패했으니 아무것도 안 올라갔다" 로 읽는다.
            raise ValueError(f'{error}. 이 실행의 객체와 _SUCCESS 는 이미 게시됐고'
                             ' 포인터만 그대로 둔다') from error
        try:
            compare_and_swap_json(s3, BUCKET, key, value, previous[1] if previous else None)
            return 'created' if current is None else 'advanced'
        except Exception:
            # 오류 코드로 분류하지 않고 결과를 다시 읽어 판정한다 (storage.put_immutable 과
            # 같은 방식). 로컬과 운영의 MinIO 버전이 달라 코드 문자열을 믿기 어렵다.
            # 두 번째도 실패하면 원인을 감추지 않고 그대로 올린다 — 권한 오류를 경합으로
            # 둔갑시키면 운영자가 있지도 않은 동시 게시자를 찾는다.
            if attempt:
                raise
    raise AssertionError('publish_pointer: 도달할 수 없는 경로')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dataset', choices=sorted(DATASETS), required=True)
    ap.add_argument('--date', '--snapshot', dest='date',
                    help='Partition date. Default: the dataset entry')
    ap.add_argument('--run-id', default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_')
                    + uuid.uuid4().hex[:8])
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id) or not 1 <= args.workers <= 16:
        ap.error('Invalid run ID or workers (1..16)')

    spec = DATASETS[args.dataset]
    date_value = args.date or spec['date']
    try:
        # The pointer decides whether to advance by comparing these as dates.
        if date.fromisoformat(date_value).isoformat() != date_value:
            raise ValueError
    except (TypeError, ValueError):
        # TypeError 는 데이터셋에 date 를 빠뜨렸을 때다 (fromisoformat(None)).
        ap.error(f'Partition date must be YYYY-MM-DD: {date_value}')

    files = select_files(spec, ROOT / spec['root'], date_value)
    names = object_names(spec, files)

    con = duckdb.connect()
    rows = {p.name: con.execute('SELECT sum(num_rows) FROM parquet_file_metadata(?)',
                                [str(p)]).fetchone()[0] for p in files}
    size = sum(p.stat().st_size for p in files)
    prefix = run_prefix(spec, date_value, args.run_id)
    pointer_key = spec['prefix'] + '/_current.json' if spec.get('pointer') else None
    print('RUN_ID=' + args.run_id, flush=True)
    print(f'{args.dataset}/{date_value}: files={len(files)} bytes={size}'
          f' rows={sum(rows.values())}', flush=True)
    for p in files:
        renamed = '' if names[p] == p.name else f' -> {names[p]}'
        print(f'  {p.name}{renamed}: {p.stat().st_size:,} bytes, {rows[p.name]:,} rows', flush=True)
    if pointer_key:
        print(f'  pointer {pointer_key} -> {spec["partition"]}={date_value}/run_id={args.run_id}',
              flush=True)

    if not args.dry_run:
        s3 = client()
        completed = exists(s3, BUCKET, prefix + '/_SUCCESS')
        if pointer_key and not completed:
            # 거부될 게시에 업로드를 먼저 태우지 않는다. 최종 판정은 publish_pointer 가
            # CAS 와 함께 다시 한다 — 그 사이에 포인터가 움직일 수 있기 때문이다.
            #
            # 이미 완료된 실행을 다시 도는 것은 게시가 아니라 전량 해시 재검증이고 버킷을
            # 바꾸지 않는다(README 가 약속한 성질). 포인터가 더 나중을 가리킨다고 그 검증까지
            # 막으면, 옛 회차가 온전한지 확인할 방법이 사라진다.
            seen = read_optional(s3, BUCKET, pointer_key)
            refuse_rollback(json.loads(seen[0]) if seen else None, date_value,
                            spec['partition'], pointer_key)

        def upload(path):
            key = prefix + '/data/' + names[path]
            with path.open('rb') as stream:
                checksum = digest(stream)
            if not exists(s3, BUCKET, key):
                # An already-finished run that is missing an object is not something
                # to quietly fill back in: _SUCCESS claims it was verified whole.
                if completed:
                    raise ValueError('Completed run missing object: ' + key)
                s3.upload_file(str(path), BUCKET, key,
                               ExtraArgs={'Metadata': {'sha256': checksum}},
                               Config=TransferConfig(use_threads=False))
            with s3.get_object(Bucket=BUCKET, Key=key)['Body'] as stream:
                actual = digest(stream)
            if actual != checksum:
                raise ValueError('Remote checksum mismatch: ' + key)
            record = {'file': 'data/' + names[path], 'bytes': path.stat().st_size,
                      'sha256': checksum, 'rows': rows[path.name]}
            if names[path] != path.name:
                # Without this the rename leaves no trace in the bucket.
                record['source_file'] = path.name
            return record

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            records = list(pool.map(upload, files))
        # No upload timestamp here on purpose. put_once refuses to overwrite an
        # object whose bytes differ, so a manifest carrying the clock would make
        # re-running the same run ID fail instead of re-verifying what is there.
        body = manifest_bytes(build_manifest(spec, args.dataset, date_value, args.run_id,
                                             records, size, sum(rows.values())))
        put_once(s3, BUCKET, prefix + '/run_manifest.json', body)
        put_once(s3, BUCKET, prefix + '/_SUCCESS', b'')
        # Last, and only now: the pointer may only name a run that is whole.
        if pointer_key:
            state = publish_pointer(s3, pointer_key,
                                    pointer_value(spec, date_value, args.run_id,
                                                  hashlib.sha256(body).hexdigest()),
                                    spec['partition'])
            print(f'_current.json {state}: {pointer_key}', flush=True)

    print(json.dumps({'dataset': args.dataset, spec['partition']: date_value,
                      'files': len(files), 'bytes': size, 'rows': sum(rows.values()),
                      'prefix': prefix, 'pointer': pointer_key, 'dry_run': args.dry_run},
                     ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
