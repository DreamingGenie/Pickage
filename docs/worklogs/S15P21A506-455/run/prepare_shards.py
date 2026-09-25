"""분할 입력을 H1 에서 곧바로 만든다(병렬 실행용).

왜 이 경로인가 — 처음에는
`historical_production prepare` → `historical_parallel convert` 두 단계로 갔다.
계산 자체는 끝났고 verify 도 통과했지만, 그 결과는 **DB 적재기가 읽지 못한다.**

`convert` 가 쓰는 매니페스트는 출처를 `source_dir`/`source_manifest_sha256` 으로 남기는데,
`FullSource` 는 `h1_dir` 과 `h1_manifest_sha256` 을 요구한다(원본 Curated 계보를 직접
확인하기 위해서다). 그래서 적재 계획을 만들 때 KeyError: 'h1_dir' 로 멈춘다.

`historical_parallel_input.prepare` 는 H1·프로필·선정 CSV 에서 곧바로 분할 입력을 쓰고
`h1_dir` 을 계보에 남긴다. 2026-09-12 전체 집계도 이 경로였다. 계산 결과는 같고
계보만 적재기가 읽을 수 있는 형태가 된다.

자원은 2026-09-12 전체 집계와 같게 둔다(메모리 16GB·임시 디스크 256GB).
기본값 40GB 로는 선언 2.45억 행을 정렬하는 단계에서 임시 디스크가 먼저 찬다.

실행 (저장소 루트에서):

  PYTHONPATH=. .venv-bq/Scripts/python.exe -B docs/worklogs/S15P21A506-455/run/prepare_shards.py
"""
from __future__ import annotations

import json
import sys
import time

from pipeline.version_dependents.historical_parallel_input import prepare

H1_DIR = "data/vd455/h1/population-20260922-v1"
H1_SHA = "c78fc9f2645932fbe59bac49b5aaaa972b8a2ffe3bb6718ee7fbfac6ceb70421"
PROFILE = "data/vd455/h5a/profile-20260922-v1/profile_manifest.json"
PROFILE_SHA = "7f94bbea236c2d322d80b7966a23a1e56affe85ca370bd4fad05ca80bf63d5b0"
# 줄끝을 LF 로 되돌린 원본. 체크아웃본은 CRLF 라 아래 SHA 와 맞지 않는다.
SELECTION = "data/vd455/selection/rerank_100k_20260922.csv"
SELECTION_SHA = "001d63149f6ca5dfe9af5bc0b92d97a02dd97d31d43da9487debf87a59c549fb"
OUTPUT = "data/vd455/h5b/shards-20260923-v1"


def main() -> int:
    started = time.monotonic()
    result = prepare(
        h1_dir=H1_DIR,
        h1_manifest_sha256=H1_SHA,
        profile_manifest=PROFILE,
        profile_manifest_sha256=PROFILE_SHA,
        selection_csv=SELECTION,
        selection_sha256=SELECTION_SHA,
        output=OUTPUT,
        full_selected=True,
        partition_count=128,
        threads=4,
        memory_limit="16GB",
        max_temp_size="256GB",
    )
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
