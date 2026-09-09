# 05. 결과와 검증

**2026-08-31 기준 패키지 11,080,940행의 통합 Curated 게시·로컬 PostgreSQL 적재·재실행 검증을 완료했다.**
[범위](01-scope.md) · [계약](06-load-contract.md) · [작업 일지](04-work-log.md) · [직접 조회 SQL](07-inspect.sql)

## 실제 적재 결과

대상은 `pickage-267-validation` 컨테이너의 `pickage_267_full_defaulted` DB(PostgreSQL 16.14)다.
다운로드는 `[2026-08-24,2026-08-31)` 합계이며, 저장소 지표는
`2026-08-31T21:01:10.517131Z` 관측 결과다. 한 패키지·기준일에 한 행을 저장했다.

| 항목 | 실제 결과 |
| --- | ---: |
| `package_snapshot` | 11,080,940행 |
| 다운로드 COMPLETE | 97,091행 |
| 다운로드 PARTIAL | 637행 |
| 다운로드 합계 보유 | 97,728행 |
| 다운로드 NULL | 10,983,212행 |
| stars 값 보유 / NULL | 7,150,485 / 3,930,455행 |
| open_issues 값 보유 / NULL | 7,150,485 / 3,930,455행 |
| 실제 0: downloads / stars / open_issues | 0 / 504,766 / 1,476,898행 |
| 다운로드 합계 대조값 | 213,093,115,787 |
| 그중 부분합 대조값 | 504,212,835 |
| 원본 대비 누락·추가 행 | 각각 0건 |
| 원본 대비 downloads·stars·open_issues 값 불일치 | 각각 0건 |

다운로드 NULL 사유는 수집 대상 밖 10,983,195행과 NOT_FOUND 17행이다.
저장소 지표 NULL 사유는 유효 저장소 없음 2,778,319행과 정확한 시각의 관측 없음 1,152,136행이다.
NULL을 0으로 바꾸거나 부분합을 제거하지 않았다. 실제 다운로드 0행은 이번 입력에 없으므로
0 보존 동작은 소형 fixture로 별도 검증했다. 여러 패키지가 같은 저장소를 사용할 수 있어
저장소 지표의 행별 합산값을 고유 저장소의 전체 합계로 해석하지 않는다.

| 패키지 | package_id | downloads | stars | open_issues |
| --- | ---: | ---: | ---: | ---: |
| react | 9,633,488 | 170,792,304 | 248,006 | 1,281 |
| typescript | 10,602,005 | 273,437,565 | 110,779 | 5,170 |

부분합 예시인 `@acuminous/bitsyntax`(package_id=72482)는 기대 7일 중 유효 6일의
453,518을 게시했다. 상태·일수·누락 사유는 통합 quality Parquet에서 확인할 수 있다.

## 실행 식별자와 품질 추적

| 항목 | 값 |
| --- | --- |
| 통합 Curated run | `package-snapshot-288-20260909-v1` |
| bucket / prefix | `pickage-curated` / `depsdev/v1/package-snapshot/snapshot=2026-08-31/run_id=package-snapshot-288-20260909-v1` |
| 통합 manifest SHA | `53b04df38d126128b30e49bd31dde4cd0354b3711317753f8165b86d9c433357` |
| 통합 입력 SHA | `2df7c37ee74c341e979d5ce21cb258af57258a240fdc233086450ed93170538c` |
| DB execution | `load-288-20260831-v1`, PUBLISHED |
| 최초 attempt | `9ca49ab318094dbb9db7bde60303ed50`, PUBLISHED |
| 재검증 attempt | `89c3d9118a0c45babf69fe1719b68de1`, REVERIFIED |

Curated 파일은 각 11,080,940행이며 총 527,062,367 bytes다.

| 파일 (`<prefix>/data/` 아래) | 크기(bytes) | 용도 |
| --- | ---: | --- |
| package_snapshot.parquet | 53,726,939 | 서비스 지표 5컬럼 |
| package_identity.parquet | 146,221,689 | 기존 DB package ID/name 대조 |
| quality.parquet | 327,113,739 | 다운로드 품질·선택 저장소·정확한 시각·NULL 근거 26컬럼 |

파일별 SHA·정책·코드 해시는 [Curated 게시 증거](evidence/curated-publication.json)에 있다.
DB `etl_load_execution.input_metadata`에 통합 manifest 전체를 저장했고,
`etl_load_attempt.quality_report`에서 입력 SHA·파일 위치·품질 요약·전수 검증 범위를 찾을 수 있다.
날짜별 다운로드 품질·미매칭 상세도 원천 key·크기·SHA로 연결했다. 추가 migration은 없다.

## 검증과 보존

| 검증 | 판정 | 근거 |
| --- | --- | --- |
| V-001 착수 문서 | 작성 당시 통과 | [당시 검사 기록](evidence/documentation-check.json), 이후 상태는 이 문서와 일지에 갱신 |
| V-002 승인 입력·DB 선행 상태 | 통과 | [45개 파일 GET/SHA·모집단 대조](evidence/input-preflight.json), [DB 사전 조회](evidence/db-preflight.json) |
| V-003 소형·격리 DB 검증 | 통과 | Curated 14 + 적재 입력 9 + 격리 DB 13 = **36개**, 실패·오류·skip 0. [테스트 기록](evidence/test-validation.json) |
| V-004 전체 Curated 게시 | 통과 | 입력·출력 키·값·품질 전수 대조, 원격 파일 GET/SHA 후 완료 표시 게시 |
| V-005 전체 DB 게시 | 통과 | 11,080,940행 INSERT·FK/ID/name·NULL 안전 값 대조와 성공 이력 동시 확정. [최초 DB 게시](evidence/db-publication.json) |
| V-006 재실행·독립 대조·보존 | 통과 | 재삽입 0건, 전체 값 재검증. DB COPY 추출을 원래 두 지표와 대조해 누락·추가·값 차이 모두 0. [독립 검증](evidence/actual-load-validation.json) |
| V-007 선행 합류·회귀 검증 | 당시 통과 | 병합 당시 83개, LF 보정 후 관련 18개 재확인. [병합 기록](evidence/merge-validation.json) |
| AC-01~AC-10 | 완료 | 입력·품질·원자적 게시·재실행·실측·인계 기준 충족. 범위는 초도 로컬 한 기준일 |

최초 execution의 `inserted=11,080,940` 기록은 유지했고 재검증 attempt에는 `inserted=0`을 남겼다.
기존 package 11,080,940행, version 54,188,349행, snapshot/reference 각 229행,
package_version_snapshot 0행을 유지했다. 선행 execution 2개·attempt 4개·current 포인터·reference
전체를 canonical JSON으로 비교한 SHA도 전후 `acc056372dde4c25426925009d9ab2d109ae656ac87fd17b68cda5982394fb53`로 같았다.
기존 기준일의 지표 보존은 격리 DB fixture에서도 확인했다.

## 실제 실행 명령

저장소 루트에서 실행했다. 아래 통합 생성 명령을 같은 입력으로 반복하면 기존 완료 결과를 재검증한다.
품질 전수 대조 비용이 크므로 단순 데이터 확인에는 [조회 SQL](07-inspect.sql)을 사용한다.

```powershell
.venv-bq\Scripts\python.exe -m pipeline.package_snapshot.build `
  --snapshot 2026-08-31 `
  --population-run-id curated-20260907-v2 `
  --population-manifest-sha256 a537f84bae78c9209e56deddb24d94cdef606d06e0e563f93ddb67e3843e71b3 `
  --candidate data/snapshot/S15P21A506-269/projects-v1/snapshot-candidate.json `
  --candidate-sha256 d22099ce22031deb47993f5c66b633d3754fd0625dbb1dcbaafc60070f8afaa7 `
  --download-run-id downloads-interval-278-20260909-v1 `
  --download-manifest-sha256 7dfc0cb5b76102d35f9baa28e03d7370bbd0d9a241b9c4a58ba3de8a95906377 `
  --repository-run-id repository-metrics-20260909-v3 `
  --repository-manifest-sha256 ca92eaa351fcd2ecd7d9355d3b5ee0635d9046ffecdb8fc946d28b226ecc0f30 `
  --run-id package-snapshot-288-20260909-v1 `
  --work-dir data/package_snapshot/curated --memory-limit 4GB --threads 2

.venv-bq\Scripts\python.exe -m pipeline.package_snapshot.load `
  --snapshot 2026-08-31 `
  --curated-run-id package-snapshot-288-20260909-v1 `
  --manifest-sha256 53b04df38d126128b30e49bd31dde4cd0354b3711317753f8165b86d9c433357 `
  --execution-id load-288-20260831-v1 `
  --docker-container pickage-267-validation --database pickage_267_full_defaulted

$env:PICKAGE_PACKAGE_SNAPSHOT_TEST_CONTAINER = 'pickage-267-validation'
.venv-bq\Scripts\python.exe -m unittest discover -s pipeline/package_snapshot -t . -v
```

실측은 위 옵션으로 Python `build.run()`과 `load.run()`을 호출했고 DB 적재는 같은 입력으로 두 번
실행했다. 표의 명령은 동일한 함수·옵션으로 연결되는 CLI 재현 형태다. 위 테스트 명령과
[조회 SQL](07-inspect.sql)은 직접 실행하여 성공을 확인했다.

| 단계 | 실제 시간 |
| --- | ---: |
| 통합 생성·품질 전수 대조·MinIO 게시 | 767.641초 |
| 최초 DB 적재·전수 대조 | 474.266초 |
| 동일 입력 DB 재검증 | 107.281초 |
| DB 추출·원래 지표와 독립 대조·보존 확인 | 35.625초 |
| 최종 36개 테스트 | 53.508초 |

Python은 기존 `.venv-bq`, DuckDB 1.5.5, 집계 메모리 제한 4GB·2 thread를 사용했다.
전체 품질의 양방향 EXCEPT ALL 검증에서 큰 임시 파일 사용을 관측했다. 성능 개선 후보는
[ISS-014](03-issues.md)에 기록했으며 검증을 생략하지 않고 완료했다.

## 남은 범위

운영 DB 이관·Spring/Flyway 애플리케이션 기동·API 검증·과거 전체 기간 적재·원격 Jira 변경은
이번 실행에 포함하지 않았다. 과거 기준일에는 그 시점의 승인 모집단·두 지표·DB 선행 이력이
별도로 필요하다. 최신 모집단을 과거 전체에 복제하지 않는다.
