# 01. 설계 메모 — package_snapshot 게시 날짜 downloads 재적재 (S15P21A506-453)

작성: 2026-09-22 11:52 KST. 구현 착수 전 컨트롤 타워 확인용.

## 실측 (읽기 전용으로 확인)

| 항목 | 값 | 출처 |
| --- | --- | --- |
| 운영 `package_snapshot` | 646,234,816행(reltuples) · 37 GB = heap 24 GB + index 14 GB | `pg_class`, `pg_total_relation_size` |
| 인덱스 | PK btree `(package_id, snapshot_at)` + **BRIN `ix_package_snapshot_history_date(snapshot_at)`** | `pg_indexes` |
| 2024-09-02 ~ 2026-08-24 | **104개 기준일 · 351,008,899행** (288 예상값과 날짜별 일치) | `GROUP BY snapshot_at` |
| 2026-08-31 (기준일) | 11,080,940행 · downloads 채움 97,728 | 같은 조회 |
| downloads 채움 수 | 최근 ~97k / 2025-02-25 이전 ~42k (10만 목록 중 벌크 API 365일 한계) | 같은 조회 |
| **운영 etl 이력** | `etl_load_execution`에 `package-snapshot`·`package-version` **0건**, `etl_snapshot_reference` **0행**, `etl_dataset_current`에 package-version **없음** | 직접 조회 |
| 운영 PG | 16.15, autovacuum on, maintenance_work_mem 64 MB, DB 149 GB | `pg_settings` |

운영 646M행은 S15P21A506-341에서 **pg_dump/restore로 이관**된 것이고 이력 표는 함께 넘어오지 않았다
(`docs/worklogs/S15P21A506-341/12-final-result.md`). 현재 적재기가 내는
`snapshot already contains rows without matching published provenance`는 정확히 이 상태(행은 있고 PUBLISHED 실행이 없음)다.

## 브리프 전제와 다른 점 2가지

1. **재적재 대상 105일 중 104일만 history 경로다.** 105번째는 기준일 2026-08-31이며 관측 경로(`build.py`/`load.py`,
   downloads-interval run)로 만든 행이다. `HistorySnapshotLoader`는 `snapshot >= base`를 거부한다.
2. **재구성 입력이 없다.** 288 실행 환경 `C:/Users/SSAFY/workspace/S15P21A506`은 삭제됐고, 그 안에 있던
   repository-metrics 후보(`quality/candidates`, 5,417만 행)·`snapshot-candidate.json`·history 상태/산출물은
   로컬 디스크·로컬 MinIO·서버 MinIO 어디에도 없다(서버 `pickage-curated`에 `repository-metrics/`·`package-snapshot-history/` prefix 비어 있음).
   남아 있는 것: population curated(로컬+서버), Projects 229일 Bronze(로컬 32 GB+서버), 10만 downloads Bronze run(서버), 로컬 일별 parquet.
   → `history.py`로 날짜별 재생성하려면 repository-metrics를 다시 돌려 후보를 만들어야 한다(수 시간). 오늘 16:44 착수 불가.

또한 운영에 이력이 없으므로 `HistorySnapshotLoader._lineage()`(package-version current·snapshot-reference 대조)는
어느 경로로든 **운영에서 통과할 수 없다.** 재적재 모드는 이 검사를 대체할 다른 근거가 필요하다.

## 선택지

### A. 원안 — 재구성 재생성 후 날짜별 DELETE→INSERT

필요: repository-metrics 재실행(후보), snapshot-candidate 재생성, 새 downloads Bronze run, 이력 부재를 우회하는 reload 모드.
장점: 정식 계보(날짜별 curated manifest·quality parquet)가 다시 생긴다. 단점: 준비만 수 시간, 오늘 시작 못 할 가능성 높음.
운영 이력이 없어 lineage 검사는 어차피 pre-image 대조로 대체해야 한다.

### B. downloads 전용 재적재 (추천)

새 모듈 `pipeline/package_snapshot/downloads_reload.py`. 기존 `postgres.py`·`history.py`는 **변경 0**.

날짜 S마다(최근부터):

1. **pre-image** = DB의 기존 행 `(package_id, stars, open_issues)` + `package.name`. 이것이 모집단이자 불변 기준.
2. **downloads 재계산**: 합본 일별 parquet에서 `[P, S)` 유효값 합. 규칙은 `history_build.py`의 `daily_aggregate`와 동일 —
   `imputed_gap` 제외, `valid_days=0 → NULL`, 실제 0 유지, BIGINT 상한 검사. P는 `snapshot` 표의 직전 날짜(229일, 288 달력과 동일).
3. staging COPY `(package_id, snapshot_at, downloads)` — 기존 행 전부(3.4M).
4. **한 트랜잭션**: pre-image 행 수·지문 재확인 → `UPDATE ... SET downloads = i.downloads WHERE s.downloads IS DISTINCT FROM i.downloads`
   → 행 수 불변·`stars`/`open_issues` 불변을 SQL로 검증(pre-image 대조) → etl 이력 기록 → COMMIT. 실패 시 그 날짜는 원래대로.
5. `VACUUM public.package_snapshot` (FULL 아님).

**DELETE→INSERT 대신 UPDATE(변경 행만)를 제안하는 이유**: 바뀌는 행은 날짜당 ~37만(= 46.9만 − 10만 중 유효값 있는 것), 전체 3.4M의 약 11%.
UPDATE는 그 행만 새 버전을 만들어 블로트가 날짜당 ~20 MB(DELETE+INSERT는 ~160 MB + 인덱스 ~70 MB), 시간도 크게 줄 것으로 예상(실측 필요).
`stars`·`open_issues`는 SET 대상이 아니라 **구조적으로 불변**이고, 대조 SQL로 한 번 더 증명한다.
DELETE→INSERT를 원하면 같은 모듈에서 스위치로 둘 수 있으나 이득이 없다.

**이력(provenance) 규칙**

- 날짜별 새 `etl_load_execution`: `dataset='package-snapshot'`, `execution_id='reload-453-<run>-<S>'`,
  `curated_run_id` = 합본 downloads Bronze run id, `manifest_sha256` = 그 run manifest SHA,
  `input_metadata` = `{policy:'package-snapshot-downloads-reload-v1', source: bronze run/prefix/sha, interval:{P,S}, preimage:{rows, fingerprint}, daily_files:[sha...]}`,
  `expected_counts={'package_snapshot': rows}`.
- `etl_load_attempt.quality_report` = `{downloads_nonnull_before, downloads_nonnull_after, changed_rows, unchanged_rows, stars_open_issues_identical: true, rows_identical: true}`.
- 운영에는 옛 실행이 없으니 supersede 표시 대상이 없다. (로컬처럼 PUBLISHED 실행이 있으면 그 `actual_counts`에 `superseded_by` 키만 추가 — 상태·건수는 덮지 않음.)
- `etl_dataset_current`는 건드리지 않는다(package-snapshot 포인터가 운영에 없고, 재적재는 기준일을 바꾸지 않음).
- 기존 "값 불일치 = 오류" 계약은 이 모듈 밖에서는 그대로다.

**`--verify-only`**: 4번까지 실행하고 ROLLBACK. 이력은 attempt `FAILED / phase VERIFY_ONLY`로 남긴다(스키마에 다른 상태가 없음).
같은 execution_id로 실제 실행하면 PREPARING으로 재등록되어 이어진다.

**입력**: 합본 46.9만 일별 parquet은 `pipeline.downloads.load --source-run <합본 run> --target-name expanded_468k_20260922.csv`로
서버 MinIO에 Bronze run으로 게시하는 것을 권장(run manifest SHA가 계보; 터널 19000 살아 있음). 게시하지 않으면 로컬 파일 SHA를 `input_metadata`에 기록한다.

**2026-08-31(기준일)**: pre-image 기반이므로 같은 모듈로 처리 가능(history/관측 구분 불필요). 포함 여부는 결정 요청.

## 리허설 계획 (로컬)

로컬 컨테이너 `pickage-local-postgres-1`에 **별도 DB `pickage_453_rehearsal`**(V1~V3 + `package` 11M 복사 + `snapshot` 229일 + 기준일 2개의 pre-image).
288 산출물이 없어 pre-image는 합성(실 `package` 이름 + 임의 stars/open_issues, 실 규모 3.4M행).
① 로컬 10만 parquet의 **절반 목록**으로 1차 적재 → ② 전체 10만으로 2차(재적재) → ③ 행 수·stars/open_issues 행 단위 동일, downloads 채움 수 증가, 이력 2건 확인, 날짜당 소요·블로트 측정.
공유 로컬 DB `pickage`는 건드리지 않는다(-454·-455 세션이 쓸 수 있음).

## 컨트롤 타워에 묻는 것

1. **A/B 선택** (B 추천). B라면 UPDATE(변경 행만) vs DELETE→INSERT.
2. **2026-08-31 포함 여부** (105번째 날짜 = 기준일, 관측 경로 데이터).
3. 합본 일별 parquet의 **Bronze run 게시** — `pipeline.downloads.load`로 서버 MinIO에 올릴지, 누가.
4. 운영 etl 이력 부재를 알고 있었는지. 재적재 시간대에 `package`·`snapshot`·`package_snapshot`을 쓰는 다른 세션(-452 package-env 등)이 있는지 — SHARE 잠금 충돌.
5. 실행 위치: 이 PC에서 `DOCKER_HOST=ssh://a506app`(COPY 날짜당 수십 MB가 SSH로) vs 서버 data 노드.
