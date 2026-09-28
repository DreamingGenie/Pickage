"""ingest_derived.py 가 게시한 파생 데이터셋을 로컬로 받는다 (S15P21A506-402).

`_current.json` 포인터가 가리키는 최신 run 의 객체를 그대로 받아온다. raw 원본이
로컬에 없는 사람이 이미 게시된 최신 산출물(예: package_text)을 구해 그 위에서
추가 가공(예: backfill_download_rank.py)을 하려 할 때 쓴다. `pointer: True`이고
`object_name`이 고정된 데이터셋만 지원한다 — 파일 하나가 정확히 무엇인지 알아야
로컬 경로 하나로 받을 수 있기 때문이다.

사용 (서버 MinIO 대상, SSH 터널이 열려 있어야 한다 — pipeline/minio/README.md
"서버 MinIO 로 적재하기" 참고):

  $env:PICKAGE_MINIO_ENV=".env.server"
  python -m pipeline.minio.fetch_derived --dataset package-text --out package_text_current.parquet
"""
import argparse
import json

from pipeline.minio.ingest_derived import BUCKET, DATASETS
from pipeline.minio.ingest_raw import client


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dataset', choices=sorted(DATASETS), required=True)
    ap.add_argument('--out', required=True, help='받아서 저장할 로컬 경로')
    a = ap.parse_args()

    spec = DATASETS[a.dataset]
    if not spec.get('pointer'):
        raise SystemExit(f'{a.dataset} 은 _current.json 포인터가 없는 데이터셋입니다 —'
                         ' 이 스크립트로는 "최신"을 알 수 없습니다')
    object_name = spec.get('object_name')
    if not object_name:
        raise SystemExit(f'{a.dataset} 은 object_name 이 고정돼 있지 않습니다(회차마다 파일이'
                         ' 여러 개일 수 있음) — 이 스크립트는 파일 하나짜리 데이터셋만 받습니다')

    s3 = client()
    pointer_key = spec['prefix'] + '/_current.json'
    body = s3.get_object(Bucket=BUCKET, Key=pointer_key)['Body'].read()
    current = json.loads(body)
    run_path = current['run_path']

    key = f"{spec['prefix']}/{run_path}/data/{object_name}"
    print(f'GET s3://{BUCKET}/{key}', flush=True)
    response = s3.get_object(Bucket=BUCKET, Key=key)
    with open(a.out, 'wb') as f:
        f.write(response['Body'].read())
    print(f"저장됨: {a.out}  (run_id={current['run_id']})", flush=True)


if __name__ == '__main__':
    main()
