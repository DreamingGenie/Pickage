# 전체 기간 패키지 스냅샷 적재

작성일: 2026-09-09. 사용자 요청으로 초도 한 기준일에서 **보유 Projects 전체 기준일**로 작업 범위를 확장했다.
초도 `2026-08-31` 적재 완료와 전체 기간 적재 완료를 구분한다. 배포일 기준 재구성 구현·대표 날짜 검증과 전체 기간 적재·최종 대조를 완료했다.

[범위](01-scope.md) · [계획](02-plan.md) · [초도 결과](05-results.md) · [이슈](03-issues.md)

## 목표와 현재 확인 결과

Projects의 `2022-05-08`~`2026-08-31` 기준일 229개를 빠짐없이 검토하여 날짜별 지표를 생성·검증하고
로컬 PostgreSQL에 적재한다. 기존 `2026-08-31`의 승인 결과는 보존한다.

2026-09-09 전체 기간 실행 전 로컬 폴더·Parquet 메타데이터와 MinIO 원격 prefix를 조회한 결과다.
아래 조사는 입력 존재·시점 확인이며 원본 전체 바이트 재검증이나 전체 지표 적재가 아니다.

| 자료 | 확인한 범위 | 전체 기간 적재에 미치는 영향 |
| --- | --- | --- |
| Projects | 229개 기준일, 2022-05-08~2026-08-31 | 저장소 지표의 과거 관측값 보유 |
| versions_full | 2026-08-31 한 시점 | 과거 시점의 실제 패키지·버전 목록은 미보유 |
| requirements | 2026-08-31 한 시점 | 과거 의존성 선언 원천은 미보유. 이번 package_snapshot 직접 계산 입력은 아님 |
| pkg_project | 2026-08-31 한 시점 | 과거 시점의 원본 매핑은 미보유. 현재 대표 저장소 구현은 versions_full.source_repo 사용 |
| 다운로드 일별 데이터 | 2024-09-01~2026-08-31, 730일 | 이전 기간은 다운로드 관측 부재. 미래 값이나 0으로 채우지 않음 |
| 지표 Curated | 다운로드 구간·저장소 지표·통합 결과 모두 2026-08-31 | 나머지 날짜의 지표 생성 필요 |
| PostgreSQL snapshot | 229개 기준일 | 기준 달력은 이미 적재됨 |
| PostgreSQL package_snapshot | 2026-08-31에만 11,080,940행 | 다른 228개 날짜는 미적재 |

전체 기간 실행 전 package_snapshot 테이블·인덱스 합계는 708,157,440 bytes, DB 전체는 25,509,157,911 bytes였다.
Windows C 드라이브 여유는 약 1.37 TB, Docker 파일시스템 여유는 약 864 GiB로 관측했다.
고정 모집단 11,080,940개를 모든 날짜에 복제하면 2,537,535,260행이 되지만, 이는 규모 참고값일 뿐
승인된 대상 집합이나 실제 적재 예정 건수가 아니다. 승인 후 배포일과 정확한 기준 시각을 독립 집계한
결과, 과거 228개 날짜에 추가할 행은 **635,138,999행**, 기존 관측 기준일을 포함한 최종 예상은
**646,219,939행**이다. 첫 날짜는 1,812,444행, 마지막 과거 날짜인 2026-08-24는 4,044,975행이다.

## 승인된 이력 구성 기준

현재 저장소 정책은 동일 SnapshotAt의 package/version 원천을 요구한다. 날짜만 바꾸거나
현재 원천의 SnapshotAt을 과거 시각으로 바꾸는 방식은 관측하지 않은 데이터를 관측값처럼 표시한다.

2026-09-09 사용자가 **“배포일 기준으로 재구성해 전체 기간 적재”**를 선택했다.
아래 첫 번째 경로를 적용하며 두 번째 경로는 이번 실행에 적용하지 않는다.

1. **배포일 기준 재구성**: 현재 승인 버전의 배포일로 해당 시점에 공개된 대상을 구성하고
   당시 후보 버전의 저장소를 선택한다. 지표에는 해당 날짜의 실제 Projects/다운로드 관측을 사용한다.
   패키지·저장소 연결은 당시 원천 관측이 아닌 재구성임을 별도 정책·manifest·품질 정보에 명시한다.
2. **과거 원천 확보**: 각 시점의 패키지·버전·저장소 원천을 추가 확보하여 기존 동일 시점 계약을 유지한다.
   원천 가용성과 수집 비용·접근 가능 여부는 조사 후 판단하며, 새 BigQuery/API 수집은 아직 수행하지 않았다.

배포일 NULL인 버전은 당시 공개 여부를 확인할 수 없어 과거 대상 판정에서 제외한다. 저장소 URL이
없더라도 공개된 승인 버전이 하나 이상이면 패키지는 포함한다. 현재 목록에서 제거된 패키지의 누락
가능성과 저장소 정보의 사후 변경 가능성을 정책·품질 정보에 기록한다.
승인 정책은 [history_policy.py](../../../pipeline/package_snapshot/history_policy.py)의
`package-snapshot-history-v1`이며 기존 관측 기반 정책과 코드는 변경하지 않는다.

실제 승인 후보 54,188,349행 중 배포일이 있는 버전은 47,172,949행이다. 배포일이 있는 승인 버전을
가진 패키지는 4,065,612개이고 모든 승인 버전의 배포일이 NULL인 패키지는 7,015,328개다.
과거 날짜의 패키지 수는 각 기준일까지 공개된 집합에 따라 달라진다. 기존 2026-08-31 관측 기반
11,080,940행은 별도 승인 결과로 그대로 보존한다.
따라서 최신 관측 기준일과 과거 재구성 기준일의 패키지 건수를 단순 비교해 신규 패키지 증가량으로
해석할 수 없다. 최신 기준일에는 배포일 미상 패키지도 포함되기 때문이다.

## 실행 계획

| 단계 | 작업 | 현재 상태 |
| --- | --- | --- |
| H-01 | 실제 달력·원천·지표 run·DB 날짜·저장 공간 조사 | 완료 |
| H-02 | 관측 이력 또는 재구성 이력의 대상·저장소·배포일 처리 계약 확정 | 배포일 기준 재구성 승인 |
| H-03 | 날짜별 입력 목록·예상 건수·원천 해시·누락 사유·분할 실행 계획 작성 | 2,679개 입력 파일의 전체 SHA 대조 및 날짜별 예상 건수 산정 완료 |
| H-04 | 날짜별 지표 생성·통합·DB 선행 이력 검사와 재개 가능한 다중 날짜 실행 구현 | 완료 |
| H-05 | 소형 다중 날짜·경계일·원자성·재실행·최신 포인터 보존 테스트 | 관련 61개 통과, 실패·skip 0 |
| H-06 | 229개 기준일에 대해 기존 승인 날짜는 보존하고 미적재 날짜를 생성·게시·적재 | 229개 기준일·646,219,939행 적재 완료 |
| H-07 | 날짜별 전체 키·값 대조, 누락 기준일·중복·NULL·부분합 검증 및 최종 결과 기록 | 승인 달력·날짜별 건수·최종 합계·기존 최신 값/포인터 보존 확인 완료 |

다운로드 원천 범위 밖 날짜도 전체 적재 대상 기준일에서 임의로 제외하지 않는다. 실제 값이 없는
지표는 NULL과 사유로 남기고, 유효한 일부 날짜만 있는 구간은 기존 부분합 정책을 유지한다.
첫 기준일의 직전 스냅샷 부재와 다운로드 수집 시작 이전 기간은 별도 사유로 구분한다.

## 구현한 확장

- 별도 `history` CLI에서 날짜별 run·해시·결과를 고정한다. `--snapshots`로 미완료 날짜만 선택할 수 있다.
- 과거 적재 전 승인된 최신 package-version 입력과 정확한 대상 snapshot-reference 시각을 확인한다.
  기존 관측 기반 적재기의 동일 시점 계약은 유지한다.
- 최신 포인터가 과거로 이동하지 않도록 기존 게시 조건을 사용하고, 실행 전후 최신 기준일의 값과
  포인터가 보존되는지 대조한다.
- 입력 SHA와 배포일별 저장소 선택 상태를 재사용한다. 선택한 날짜의 품질·전체 서비스 값은 검증하며,
  중단 후 재개할 때는 이미 PUBLISHED인 날짜를 실행 목록에서 제외해 반복 비용을 줄인다.

## 현재 실제 수행 범위

로컬·MinIO 입력 inventory와 DB/디스크 읽기 전용 조사, 승인 manifest에 대한 로컬 입력 2,679개
파일의 bytes/full SHA 대조를 완료했다. 입력 SHA는
`f3cd069f5d9eae475b55d615c2597e922a423554838b2f722686e747412023d1`이다.
Projects 각 날짜의 유일한 승인 Bronze run은 `bronze-20260907-v1`이다. 로컬 `_MANIFEST.json`에는
전체 파일 해시가 없지만 원격 승인 `run_manifest.json`에는 파일별 SHA가 있으며 이를 사용했다.
이번 입력 검증은 로컬 전체 SHA와 승인 원격 manifest의 대조이며 원격 원본 전체 바이트의 재다운로드는 아니다.
기존 기준일의 서비스 데이터·원천 객체를 보존했다. 날짜별 검사에서 전체 누적 테이블을 반복 읽는 비용을 줄이기 위해 로컬 검증 DB에
`ix_package_snapshot_history_date` BRIN 인덱스(`snapshot_at`, `autosummarize=on`)를 추가했다.
서비스 컬럼·제약과 Flyway migration은 보존했다. 이는 로컬 실행 인덱스이며 운영 서버 적용을 의미하지 않는다.
전체 기간 결과는 H-07까지 실제 검증했으며 [최종 검증 기록](evidence/history-full-load-validation.json)에 남겼다.

## 대표 기준일 실제 검증

| 기준일 | 실제 적재 행 | 확인한 경계 |
| --- | ---: | --- |
| 2022-05-08 | 1,812,444 | 직전 스냅샷 없음, 다운로드 합계 NULL |
| 2024-09-02 | 2,988,876 | `[2024-08-29,2024-09-02)` 중 수집 가능한 날짜만 부분합 |
| 2026-08-24 | 4,044,975 | 최근 과거 버전 선택과 전체 7일 구간 |

합계 8,846,295행을 생성·게시·적재하고 DB 서비스의 모든 키·값을 대조했다.
별도로 원래 버전 후보에 직접 배포일 필터와 ROW_NUMBER를 적용하고, Projects의 원본 지표 쌍과
일별 다운로드를 다시 집계하여 생성 결과와 대조했다. 세 날짜 모두 대상·이름·선택 버전·저장소·
각 지표 값 차이와 중복이 0이었다. 이 독립 원천 대조는 대표 세 날짜에 대한 검사다.
기존 2026-08-31 행의 값 지문·합계·건수와 최신 포인터도 동일했다.

- [대표 날짜 적재 증거](evidence/history-representative-load.json)
- [독립 원천 대조 증거](evidence/history-independent-source-check.json)
- [날짜별 예상 건수](evidence/history-expected-counts.json)
- [DB에서 직접 진행 상황 조회](09-inspect-history.sql)

## 실제 실행·재개 명령

입력 설정의 로컬 경로는 이 검증 환경의 승인 파일 위치다. 다른 환경에서는 동일 원격 run/SHA에
대응하는 파일을 준비하고 로컬 경로를 맞춘다. run ID와 입력·코드 해시가 바뀌면 같은 실행을 재사용할 수 없다.

```powershell
.venv-bq\Scripts\python.exe -m pipeline.package_snapshot.history `
  --config data/package_snapshot/S15P21A506-288/history-preflight/history-config.json `
  --run-id full-history-288-20260909-v1 `
  --work-dir data/package_snapshot/history `
  --docker-container pickage-267-validation `
  --database pickage_267_full_defaulted --memory 8GB --threads 4
```

원본·품질·서비스 Parquet는 날짜별 immutable run에 게시한다. 위 명령을 그대로 재실행하면 이미 게시한
날짜도 전수 재검증하므로, 중단 지점부터 이어갈 때는 아래처럼 미완료 날짜만 지정한다.

```powershell
$publishedDates = @(docker exec pickage-267-validation psql -X -At -U postgres `
  -d pickage_267_full_defaulted -c "SELECT snapshot_at FROM public.etl_load_execution WHERE dataset='package-snapshot' AND status='PUBLISHED';")
if ($LASTEXITCODE -ne 0) { throw '게시 이력 조회 실패' }
$plan = Get-Content data/package_snapshot/S15P21A506-288/history-preflight/expected-date-counts.json -Raw | ConvertFrom-Json
$remaining = @($plan.dates.snapshot_at | Where-Object { $_ -notin $publishedDates -and $_ -ne '2026-08-31' })
if ($remaining.Count -gt 0) {
  .venv-bq\Scripts\python.exe -m pipeline.package_snapshot.history `
    --config data/package_snapshot/S15P21A506-288/history-preflight/history-config.json `
    --run-id full-history-288-20260909-v1 --work-dir data/package_snapshot/history `
    --docker-container pickage-267-validation --database pickage_267_full_defaulted `
    --memory 8GB --threads 4 --snapshots $remaining
}
```

재개 전 기존 적재 프로세스가 종료됐는지 확인한다. 강제 종료된 PREPARING 시도는 다음 실행에서
ABANDONED 실패 이력으로 남고, 해당 날짜는 새 attempt로 처리한다. 같은 날짜가 이미 커밋됐다면
PUBLISHED 이력으로 제외되며 중복 삽입하지 않는다. 로컬 결과는
`data/package_snapshot/history/full-history-288-20260909-v1/<기준일>/result.json`에 남는다.
선택 실행도 종료 시 DB 전체 날짜별 건수와 기존 기준일 보존을 검사하지만 결과 상태는
`SELECTED_DATES_PUBLISHED`다. 따라서 status만으로 전체 완료를 판단하지 않는다.
최종 DB 날짜 집합이 승인 달력의 229개 날짜와 일치하고, 날짜별 건수가 예상 건수와 같으며,
합계 646,219,939행·기존 최신 값/포인터 보존이 확인돼야 전체 기간 완료로 기록한다.

## 2026-09-10 재부팅 후 재개와 최종 완료

재부팅 후 DB 실행 이력에서 219개 기준일·606,965,179행의 PUBLISHED와 `2026-06-15`의
중단된 PREPARING을 확인했다. 최초 재개는 전체 날짜를 다시 검증했으나 이를 중단하고,
미완료 10개 날짜만 `--snapshots`로 지정해 08:45 KST에 다시 시작했다. 실행 중 코드·입력 해시는 보존했다.

재개 후 MR 준비 시점에는 **226개 기준일·634,222,702행 PUBLISHED**와 1개 PREPARING을 확인했다.
최종 실행은 **2026-09-10 09:38:39 KST**(00:38:39 UTC)에 종료됐고, **229개 기준일·
646,219,939행**과 기존 최신 값·포인터 보존을 확인했다. 결과 상태는 선택 실행의 의미를 보존하는
`SELECTED_DATES_PUBLISHED`이며, 승인 달력·날짜별 건수·합계 검증을 함께 적용해 전체 완료로 판정했다.
세 대표 날짜의 독립 원천 대조는 별도 증거로 유지한다.

실행 이력에는 실패 attempt 2건도 함께 남아 있다. `2026-06-15`는 재부팅으로 중단됐고,
`2022-06-27`은 전체 재검증을 사용자 요청으로 중단하면서 최신 attempt가 `FAILED/ABANDONED`로
기록됐다. `2026-06-15`는 재개 후 새 시도에서 적재에 성공했고, `2022-06-27`은 최초 적재 행과
성공 검증 보고서가 유지됐다. 최종 날짜별 행 수는 예상값과 일치한다. 따라서 전체 완료는 모든 attempt의 성공이 아니라 PUBLISHED 날짜 집합, 실제
DB 대조, 성공 attempt 근거를 함께 확인해 판정했다.

운영 서버·애플리케이션 기동은 여전히 미실행이다.

마지막 10개 기준일에서 39,254,760행을 추가했으며, 입력 확인과 종료 검증을 포함한 해당 재개 실행은
3,205.407초(약 53분 25초) 걸렸다. 이는 중단 전 실행 시간을 제외한 마지막 재개 실행의 시간이다.

새 로그는 `resume-remaining-20260910.log`, 오류 로그는 `resume-remaining-20260910.stderr.log`다.
둘 다 위 실행의 로컬 루트 아래에 있다. 최종 판정 근거는 [최종 검증 기록](evidence/history-full-load-validation.json)이다.
