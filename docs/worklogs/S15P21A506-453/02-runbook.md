# 02. 운영 실행 기록 — downloads 재적재 명령·기대 출력·복구

[설계 메모](01-design.md) · 모듈 [`downloads_reload.py`](../../../pipeline/package_snapshot/downloads_reload.py) ·
모듈 설명 [README](../../../pipeline/package_snapshot/README.md#게시된-기준일의-downloads-재적재-s15p21a506-453)

실행 위치는 전진님 PC의 PowerShell 창이다. `DOCKER_HOST=ssh://a506app`로 로컬 도커 CLI가 운영 데몬을 보게 하고,
psql은 운영 컨테이너 `pickage-app-postgres-1` 안에서 돈다(`pipeline/dependent_transitions/load.py` 문서와 같은 방식).
전송 CSV는 날짜당 약 15 MB(46.9만 이름 × 4열)가 SSH로 흘러간다.

## 0. 입력 (컨트롤 타워가 넘긴다)

| 항목 | 값 |
| --- | --- |
| 합본 일별 parquet 루트 (`--daily-root`) | _(16:41 이후 수령)_ |
| Bronze run id (`--bronze-run-id`) | _(수령)_ |
| Bronze manifest SHA-256 (`--bronze-manifest-sha256`) | _(수령)_ |
| 재적재 run id (`--run-id`) | `downloads-468k-20260922-v1` |

`--daily-root`에는 `downloads/date=YYYY-MM-DD/*.parquet`(2024-09-01~2026-08-31)와 `downloads_status.parquet`가 있어야 한다.

## 1. 사전 확인 (읽기 전용)

```powershell
$env:DOCKER_HOST='ssh://a506app'
docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -X -At -c "SELECT count(*) FROM etl_load_execution WHERE dataset='package-snapshot';" -c "SELECT pg_size_pretty(pg_relation_size('package_snapshot')), pg_size_pretty(pg_indexes_size('package_snapshot'));"
```

기대: 첫 값 `0`(이 작업 전에는 package-snapshot 실행이 없다), 크기 `24 GB | 14 GB` 근처.

## 2. verify-only (DB를 바꾸지 않는다)

기준일 2개(가장 최근 둘)로 먼저 돈다. 검사·UPDATE까지 실행한 뒤 ROLLBACK 한다.

```powershell
cd C:\git\S15P21A506; $env:DOCKER_HOST='ssh://a506app'; .\.venv-bq\Scripts\python.exe -m pipeline.package_snapshot.downloads_reload --daily-root <합본 루트> --bronze-run-id <run> --bronze-manifest-sha256 <sha> --run-id downloads-468k-20260922-v1 --snapshots 2026-08-31 2026-08-24 --docker-container pickage-app-postgres-1 --database pickage --db-user pickage --verify-only
```

기대 출력(JSON 한 줄씩):

- `STAGING_READY` — `staging_rows` ≈ 46.8만(합본 이름 중 그 구간에 일별 행이 있는 이름), `daily_dates` 7.
- `SNAPSHOT_COMPLETE` — `action: VERIFY_ONLY`, `nonnull_before` 97,728(08-31) / 97,675(08-24),
  `changed_rows` ≈ 36만대. 이 값이 실제 실행에서 바뀔 행 수다.
- 실패 `recomputed downloads differ from published values: mismatched=N missing_from_staging=M`이면
  **그 날짜는 변경 없이 끝났다.** 합본 parquet이 기존 10만의 일별 값을 그대로 담지 않은 것이므로 컨트롤 타워에 보고하고 멈춘다.

기대 수치의 근거: 확장 목록 46.9만 중 **8,738개는 Curated 스냅샷에 없는 이름**이라 UPDATE 대상 행이 없다(컨트롤 타워 집계).
그래서 `acceptance.staging_unmatched`는 최소 8,738이고, 여기에 그 날짜에 행이 없는 이름(모집단 밖·배포일 이후)이 더해진다.
"갱신 0인 패키지" 수를 해석할 때 이 값을 기대치로 쓴다.

verify-only 뒤 DB에는 `etl_load_execution` 2건이 `FAILED`, attempt가 `FAILED / VERIFY_ONLY`로 남는다. 서비스 행은 그대로다.

**verify-only와 실제 실행 사이에 코드를 바꾸거나 rebase 하지 않는다.** 모듈의 `contract_sha256`은
`downloads_reload.py`와 `downloads_interval/aggregate.py` 두 파일의 해시다(마이그레이션은 포함하지 않는다).
같은 실행 ID의 `FAILED` 등록에 다른 해시로 오면 `execution_id already exists with different input or contract`로 거부된다.
실행 시점의 해시는 `data/package_snapshot/downloads_reload/<run-id>/plan.json`의 `contract_sha256`에 있다.
**고정 기대값으로 여기 적지 말고, 실행 시점 값을 Jira -453 코멘트에 기록한다.**

```powershell
docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -X -At -c "SELECT execution_id,status,error_message FROM etl_load_execution WHERE dataset='package-snapshot' ORDER BY created_at;"
```

## 3. 실제 실행 (컨트롤 타워 신호 후)

같은 run id로 105일 전체. 최근 기준일부터 내려간다. 출력을 **파일로 리다이렉트하지 말 것**(cp949 크래시). 필요하면 `Tee-Object`가 아니라 창을 그대로 둔다.

```powershell
cd C:\git\S15P21A506; $env:DOCKER_HOST='ssh://a506app'; .\.venv-bq\Scripts\python.exe -m pipeline.package_snapshot.downloads_reload --daily-root <합본 루트> --bronze-run-id <run> --bronze-manifest-sha256 <sha> --run-id downloads-468k-20260922-v1 --from 2024-09-02 --to 2026-08-31 --docker-container pickage-app-postgres-1 --database pickage --db-user pickage
```

verify-only에 쓴 두 날짜는 같은 execution_id가 `FAILED`로 있으므로 `PREPARING`으로 재등록되어 정상 게시된다.

날짜마다 `package`·`snapshot`에 SHARE, `package_snapshot`·etl 표에 SHARE ROW EXCLUSIVE 잠금을 잡는다(읽기는 막지 않음).
다른 세션이 `package`를 쓰고 있으면 `lock_timeout 10s`에 그 날짜가 실패로 끝나고 실행이 멈춘다 — 재적재 슬롯은 단독이어야 한다.

날짜마다 `SNAPSHOT_COMPLETE`에 `seconds`(소요)와 `maintenance.sizes_*`(heap/index 바이트)가 찍힌다.
**날짜당 소요가 5분을 넘거나 heap+index 증가가 날짜당 50 MB를 넘으면 보고한다**(리허설 실측 기준은 4절).

날짜별 결과 파일: `data/package_snapshot/downloads_reload/downloads-468k-20260922-v1/<S>/report.json`.
전체 요약: 같은 폴더의 `result.json`(`status: RELOADED`, `changed_rows` 합계).

## 4. 리허설 실측 (로컬 `pickage_453_rehearsal`, 2026-09-22 12:15~12:20)

로컬 컨테이너 `pickage-local-postgres-1`에 별도 DB를 만들어 V1~V3 + `package` 11,080,940행 복사 + 달력 109일 +
기준일 2개의 **합성 pre-image**(288 산출물이 없어 stars·open_issues는 난수, downloads는 NULL) + 운영과 같은 BRIN.
288 실데이터가 아니므로 값의 대표성은 없고, **기계적 동작·소요·블로트·불변 대조**를 재는 리허설이다.

| 단계 | 입력 | 08-31 (11,080,940행) | 08-24 (4,029,434행) |
| --- | --- | ---: | ---: |
| 1차 UPDATE | 10만 중 절반(49,607명) | 48,450행 · 16.7 s | 17,521행 · 11.6 s |
| 2차 verify-only | 전체 10만(99,215명) | mismatched **0** / kept_equal 48,450 · ROLLBACK · 21.3 s | mismatched **0** / kept_equal 17,521 · 22.3 s |
| 2차 UPDATE | 전체 10만 | 49,278행 · 27.4 s (VACUUM 7.5 s 포함) | 17,831행 · 24.3 s |
| 블로트 (heap / index) | 2차 UPDATE 49,278행 | +2.5 MB / +0.5 MB | +0 / +0 |

- **(c) 일치율**: 기존 non-NULL 값의 재계산 일치율 100% (두 날짜 모두 `mismatched=0`, `missing_from_staging=0`).
- **(a) 소요**: 날짜당 12~27초. 소요의 대부분은 3.4M~11M행 지문 계산 2회와 UPDATE다. 운영은 행이 3.4M(기준일 11M)이고
  바뀌는 행이 약 37만(리허설 5만의 7배)이므로 **날짜당 1~3분**으로 본다(SSH 전송·서버 디스크는 미측정). 105일 ≈ **2~5시간**. 8.1 h 추정은 폐기.
- **(b) 블로트**: 49k 갱신에 heap +2.5 MB → 37만 갱신 ≈ **+19 MB/일**, index +0.5 MB → 105일 합계 약 **2 GB**. 배정 3 GB 안.
  DELETE→INSERT였다면 날짜당 +230 MB였다.
- 독립 대조(모듈 밖 SQL, pre-image 사본과 LEFT JOIN): 두 날짜 모두 `rows_added 0 · stars_issues_changed 0 ·
  existing_downloads_changed 0`, `newly_filled` = 모듈이 보고한 `changed_rows`.
- 이력: `rehearsal-half` 2건 PUBLISHED, `rehearsal-full` 2건은 attempt `FAILED/VERIFY_ONLY` → 같은 실행 ID로 `PUBLISHED/COMMIT`.
  `etl_dataset_current.package-snapshot` = `reload-453-rehearsal-full-2026-08-31`.
- 부수 확인: 로컬 10만 parquet로 재계산한 08-31 채움 수 **97,728**은 운영의 현재 08-31 채움 수와 정확히 같다.
  같은 규칙·같은 입력이 운영 값을 만들었다는 정황이다(운영 verify-only가 이를 확정한다).

3절의 보고 기준(날짜당 5분·+50 MB)은 이 실측의 2~3배 여유다.

## 5. 중단·복구

- **중단 후 재개**: 같은 명령에 `--skip-published`를 붙인다. 이미 `PUBLISHED`인 날짜는 건너뛰고, 진행 중이던 날짜는
  트랜잭션이 통째로 롤백돼 있으므로 새 attempt로 다시 처리된다(강제 종료된 attempt는 다음 실행이 `ABANDONED`로 표시).
- **acceptance 실패로 멈춤**: 그 날짜 이후(더 오래된 날짜)는 시작되지 않는다. 이미 게시된 최근 날짜는 유효하다.
  원인은 합본 입력이다. 입력을 고쳐 **새 run id**로 다시 돈다(같은 run id는 입력 SHA가 달라 등록이 거부된다).
- **되돌리기**: 이 재적재는 NULL이던 자리를 값으로 바꾼 것뿐이라 되돌릴 대상은 "새로 채운 값"이다.
  각 날짜의 attempt `quality_report.acceptance.newly_filled`가 그 수다. 되돌리려면 합본에서 추가분 이름을 뺀
  10만 루트로 같은 모듈을 새 run id로 돌리면 된다 — 단, 10만 루트에 없는 이름은 재계산 대상이 아니라 UPDATE 되지 않으므로
  실제 되돌림은 `UPDATE package_snapshot SET downloads=NULL WHERE ... name IN (추가분)`을 날짜별로 직접 실행해야 한다.
  이 SQL은 이 문서에 넣지 않는다. 필요해지면 컨트롤 타워와 함께 쓴다.
- **COMMITTED_UNVERIFIED**: 커밋 뒤 확인 연결이 끊긴 경우다. 같은 명령을 다시 돌리면 `REVERIFIED`로 값만 대조한다.

## 6. 완료 확인

```powershell
docker exec -i pickage-app-postgres-1 psql -U pickage -d pickage -X -At -c "SELECT count(*) FILTER (WHERE status='PUBLISHED'), count(*) FROM etl_load_execution WHERE dataset='package-snapshot' AND execution_id='reload-453-downloads-468k-20260922-v1-'||snapshot_at::text;" -c "SELECT snapshot_at, count(downloads) FROM package_snapshot WHERE snapshot_at IN (DATE '2026-08-31', DATE '2026-08-24', DATE '2024-09-02') GROUP BY 1 ORDER BY 1;"
```

기대: `105 | 105`, 채움 수가 각각 97,728 → 약 46만 / 97,675 → 약 46만 / 41,820 → (2024-09-02는 벌크 API 365일 한계로 적게 는다).
