# 03. MR 본문 초안 (GitLab 웹 플레인텍스트 편집기에 붙일 원문)

제목: `feat: 게시된 기준일의 downloads 재적재 모듈 (S15P21A506-453)`

---

## 개요

운영 `package_snapshot`(229개 기준일·646M행)의 `downloads`를 10만 → 46.9만 패키지로 넓히기 위해, **이미 게시된 기준일의
downloads만 다시 계산해 값이 바뀌는 행만 UPDATE** 하는 별도 모듈을 추가한다.
원안(history 경로로 날짜를 다시 만들어 DELETE→INSERT)은 운영에 etl 이력이 없고(-341 pg_dump 이관) 288 재구성 입력이
소실돼 성립하지 않았다. 기존 두 적재 경로(`postgres.py`·`history.py`)의 계약은 건드리지 않는다.

### 관련 이슈

이슈 번호 : S15P21A506-453

### 변경 영역

- [x] 데이터 수집/파이프라인 (배치·스트리밍·스케줄러)
- [x] 데이터 저장소 (스키마·테이블·마이그레이션) — 스키마 변경 없음, `package_snapshot.downloads` 값 갱신과 etl 이력 추가
- [ ] 분석/모델 (AI, 피처, 학습·추론)
- [ ] 백엔드 API
- [ ] 프론트엔드 / 시각화
- [ ] 인프라·설정·CI
- [x] 문서

## 작업 상세 내용

`pipeline/package_snapshot/downloads_reload.py` (신규)

- **모집단·stars·open_issues는 기존 행이 정본**이다. 세 값은 대입하지 않고, 트랜잭션 안에서 행 수와
  `(package_id, stars, open_issues)` 지문이 전후 동일함을 확인한다.
- **P**는 `public.snapshot`의 `LAG(snapshot_at)` — 백엔드 `DOWNLOADS_TREND_SQL`과 같은 정의.
- **downloads 규칙**은 `pipeline/downloads_interval/aggregate.py`의 `[P,S)` 집계 문장을 그대로 쓴다
  (`imputed_gap`·NULL 제외 유효값 합, 유효 일수 0 → NULL, 실제 0 유지). 검증 헬퍼(`require_schema`·`reject`)도 import.
- **적용 전 검사(회귀 검사)**: 기존 `downloads IS NOT NULL` 행의 재계산값이 **전부** 같아야 UPDATE 한다.
  하나라도 다르거나 일별 데이터가 없으면 그 날짜는 변경 없이 실패로 끝난다. 이 검사가 통과하면 나머지 추가분 UPDATE의
  정당성이 따라온다(기존 10만의 현재 값이 정답지).
- **UPDATE는 변경 행만** (`downloads IS DISTINCT FROM 재계산값`). 날짜당 약 37만 행. 블로트 약 +19 MB/일.
- **이력**: `PackageSnapshotLoader.start()`를 그대로 재사용해 날짜별 `etl_load_execution('reload-453-<run>-<S>')`를 등록하고,
  attempt `quality_report`에 채움 수 전후·변경 행 수·불변 대조 결과·staging 통계를 남긴다. `etl_dataset_current`의
  `package-snapshot` 포인터는 가장 늦은 기준일을 가리킨다(운영에는 없던 포인터, 컨트롤 타워 허용).
- **`--verify-only`**: UPDATE까지 실행하고 ROLLBACK. attempt는 `FAILED / VERIFY_ONLY`. 같은 실행 ID로 다시 돌리면 게시.
  게시 후 같은 실행 ID는 `REVERIFIED`(값 대조만).
- 순서는 최근 기준일부터. 날짜마다 `VACUUM`(FULL 아님). 중단 후 `--skip-published`로 재개.

`pipeline/package_snapshot/test_downloads_reload.py` (신규, 7개) — 재계산 규칙 일치·READY 아닌 이름 거부 / 변경 행만 UPDATE·이력 기록 /
기존값 불일치·일별 데이터 부재 시 무변경 중단 / verify-only 롤백 후 게시 / 재실행 REVERIFIED.

문서 — README 절, `docs/worklogs/S15P21A506-453/01-design.md`(실측·선택지·결정), `02-runbook.md`(운영 명령·기대 출력·복구·리허설 실측).

## 데이터·파이프라인 영향 (해당 시)

- 스키마/테이블 변경 : 없음. `package_snapshot.downloads` 값만 갱신(NULL → 값). `etl_load_execution`·`etl_load_attempt`에 날짜별 이력 추가,
  `etl_dataset_current`에 `package-snapshot` 포인터 신설.
- 기존 적재 데이터 재처리(backfill) 필요 여부 : 이 MR이 그 backfill 도구다. 운영 실행은 2024-09-02~2026-08-31 105개 기준일,
  컨트롤 타워 신호 후 단독 슬롯에서 실행. 리허설 실측 기준 날짜당 1~3분 → 2~5시간, 블로트 약 2 GB(배정 3 GB 안).
- 외부 API 호출량·키 사용 변화 : 없음(입력은 이미 수집된 일별 Bronze parquet).
- 배치 주기·실행 시간 변화 : 없음(1회성).

## 실행·검증 방법

```powershell
$env:PICKAGE_PACKAGE_SNAPSHOT_TEST_CONTAINER = 'pickage-local-postgres-1'
.\.venv-bq\Scripts\python.exe -m unittest pipeline.package_snapshot.test_downloads_reload -v
```

- [x] 로컬에서 실행/테스트 확인 — 7개 통과. 기존 `test_contract`·`test_history_contract`·`test_history_postgres` 포함 23개 OK(계약 해시 불변).
- [x] 샘플 데이터로 결과 검증 — 로컬 별도 DB `pickage_453_rehearsal`(package 11,080,940행 복사 + 합성 pre-image 15,110,374행)에서
  10만 절반 → 전체로 2단계 재적재. 재계산 == 기존값 일치율 100%(불일치 0/48,450·0/17,521), UPDATE 49,278행 27.4초 / 17,831행 24.3초,
  heap +2.5 MB. 모듈 밖 SQL로 pre-image 사본과 대조: 행 추가 0·stars/open_issues 변경 0·기존 downloads 변경 0.
  상세는 `02-runbook.md` 4절.

## 자체 리뷰 결과 (base 대비 diff 인라인)

`/code-review`는 돌리지 않았다. base(`develop`) 대비 diff를 직접 읽어 동작 결함·설계 결함·빠뜨린 것을 확인했고,
발견한 결함 1건을 이 MR 안에서 고쳤다(커밋 `1f85fd3`).

- **막는 것 (고쳤음)**: `--skip-published`의 `execution_id LIKE 'reload-453-<run>-%'`에서 run id의 `_`가
  LIKE 한 글자 와일드카드로 해석됐다. `SAFE_ID`가 run id에 `_`를 허용하므로, 밑줄 자리만 다른 다른 run의 게시 날짜를
  이미 끝난 것으로 보고 건너뛸 수 있었다. 패턴 생성 시 `_`를 이스케이프한다.
- **MR 노트 (고치지 않음, 의도)**: `VACUUM`은 검증된 COMMIT 뒤에 돈다. 그 단계에서 실패하면 그 날짜는 이미 게시된 것이므로
  보고서 상태를 `PUBLISHED_MAINTENANCE_FAILED`로 구분해 남긴다(롤백하지 않는다).
- **확인하고 넘긴 것**: 잠금 순서는 기존 적재기와 같다(`package`·`snapshot` SHARE → `package_snapshot`·etl SHARE ROW EXCLUSIVE).
  `_literal`을 통과하지 않는 SQL 삽입 지점은 없다(날짜는 달력 조회 결과, run id·DB 이름은 정규식 검사).
  `reverify` 경로는 UPDATE를 하지 않고 값만 대조한다. staging COPY 파일의 이름은 DuckDB에서 TSV 이스케이프한다.

## 리뷰 요청 사항

- 적용 전 검사의 판정 조건(`mismatched=0 AND missing_from_staging=0`)이 "기존 값이 정답지"라는 수용 기준을 충분히 표현하는지.
- `run()` 오케스트레이터(달력·순서·`--skip-published`)는 단위 테스트가 없고 리허설 CLI 실행으로만 확인했다.
- `snapshot_timestamp`에 관측 시각이 없어 S의 00:00:00 UTC를 넣고 manifest에 그 사실을 적었다. 더 나은 표기가 있으면 의견 요청.
- 운영 실행 결과(105일 소요·블로트·채움 수)는 실행 후 Jira -453 코멘트와 `02-runbook.md`에 추가한다. 이 MR은 코드·문서 범위다.

## 체크리스트

- [x] 브랜치명이 `<part>/<type>/<이슈키>-작업내용` 규칙에 맞습니다 (AGENTS.md 4번 항목)
- [x] API 키·계정 정보 등 시크릿이 커밋에 포함되지 않았습니다
- [ ] 리뷰어와 라벨을 지정했습니다
- [x] 관련 Jira 이슈 상태를 갱신했습니다

🤖 Generated with [Claude Code](https://claude.com/claude-code)
