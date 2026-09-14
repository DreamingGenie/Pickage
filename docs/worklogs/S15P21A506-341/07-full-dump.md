# M3 — 전체 압축 덤프와 원본 검증값

이 문서는 해당 단계 당시의 계획·검증 기록이다. 이후 서버 복원과 서비스 DB 전환을 완료했으며, 현재 상태와 검증 범위는 [최종 결과](12-final-result.md)를 따른다. 당시 실패·미실행 기록은 이력으로 보존한다.

## 실행 범위

기존 로컬 DB의 `package`, `version`, `snapshot`, `package_snapshot`,
`package_version_snapshot`과 229개 자식을 대상으로 한다. CSV를 만들거나 의존 수를 다시 계산하지 않는다.
서버 전송/복원·서비스 연결 전환은 M4 이후 별도 단계다.

`prepare_full_dump.py`는 같은 DB 기준 시점에서 다음을 순서대로 수행한다.

1. 읽기 전용 REPEATABLE READ 세션을 열고 대상 테이블에 ACCESS SHARE 잠금을 잡는다.
2. `pg_export_snapshot()`으로 데이터 기준 시점을 공유한다.
3. `pg_dump -Fd -j4 --compress=zstd:1 --snapshot=<token>`으로 바로 압축 덤프한다.
4. TOC의 234개 테이블 정의와 233개 데이터 항목, 파일 목록/SHA-256을 확인한다.
5. 검증 연결 두 개가 같은 snapshot을 가져와 exact count와 모든 행의 값 서명을 계산한다.
6. 기준값·archive manifest를 연결하는 검증 manifest를 만들고 보관 세션을 닫는다.

여기서 DB의 MVCC snapshot은 서비스 테이블에 저장된 229개 관측 날짜와 다른 개념이다.
원본에 새 DML이 발생해도 고정한 시점 이후의 데이터는 덤프/검증 양쪽에서 제외된다.
대상 테이블·파티션의 DDL은 실행 중 피해야 한다. DDL 잠금 경쟁은 30초 안에 실패시키며 자동 재시작하지 않는다.

이 방식은 PostgreSQL 16 공식 문서의 [스냅샷 공유](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION),
[SET TRANSACTION](https://www.postgresql.org/docs/16/sql-set-transaction.html),
[pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html),
[상속 테이블 잠금](https://www.postgresql.org/docs/16/sql-lock.html)을 기준으로 구현했다.

## 실행 위치와 상태

최초 실행은 2026-09-14 14:56 KST 시작 후 상태 파일 교체 오류로 실패했다.
수정한 코드로 **2026-09-14 15:55 KST 재실행**했다.

- 원본: `pickage-267-validation` / `pickage_267_full_defaulted`
- 현재 실행 폴더: `data/service-data-migration/341/local-dump-probe/full-20260914T065517Z`
- 재실행 PID: `14216` (프로세스가 살아 있는지는 조회 시 다시 확인)
- 이전 실패 폴더: `full-20260914T055613Z`, 이전 PID `27280` 종료 확인
- 동결한 실행 코드: 실행 폴더의 `code/`
- 실제 실행 코드 해시: `status.json`의 `code_sha256`
- 최신 실행 경로: `data/service-data-migration/341/latest-full-run.txt`
- 실행 순서: dump jobs=4 → 원본 검증 workers=2 → 최종 파일 검증
- 전체 시간제한 없음. 서버/클라이언트 전역 설정은 바꾸지 않고 해당 세션의 statement/idle timeout만 해제한다.

착수 시 원본에 다른 연결이 없었고, 로컬 디스크 여유 약 1TiB, 원본 PVS OID 280767과 자식 229개를 확인했다.
실행은 숨김 백그라운드 프로세스로 시작해 채팅의 지속적인 확인을 요구하지 않는다.

상태 확인:

```powershell
$runDir = (Get-Content data/service-data-migration/341/latest-full-run.txt -Raw).Trim()
Get-Content (Join-Path $runDir 'status.json') -Raw
```

- `RUNNING`: 진행 중. `phase`, `completed_relations`, `active_relations`로 단계를 확인한다.
- `M3_COMPLETE`와 `ready_for_transfer=true`: 덤프와 원본 검증값이 모두 완성됐다는 뜻이다.
- `FAILED`: 로그를 확인한다. 실패한 폴더/다른 snapshot의 결과를 섞어 재개하지 않는다.
- 상태 파일은 단계 또는 테이블 완료 때 갱신하므로 큰 단일 테이블을 처리하는 동안 수정 시각이 오래 그대로일 수 있다.
- `ready_for_service=false`는 M3가 끝나도 유지한다.
- 상태 파일이 잠겨 교체되지 않으면 `status-fallback/`에 그 시점의 상태를 저장하고 계산은 계속한다.
- 최종 결과는 변경 중인 상태 파일과 별도로 **`result.json`**에 기록한다. 해당 파일이 있으면 최종 상태를 우선 확인한다.

현재 문서는 시작 기록이다. 실제 완료 여부는 해당 실행의 `status.json`으로 확인한다.

## 산출물

| 경로 | 내용 |
| --- | --- |
| `archive/`, `archive-manifest.json` | 압축 directory dump, 파일별 크기/SHA와 snapshot token |
| `archive-toc.txt` | 실제 포함한 테이블/데이터/제약/인덱스 목록 |
| `source-catalog.json` | 원본 DB 식별자, 테이블 OID·컬럼·파티션 경계, 관측 날짜 목록 |
| `source-receipts/*.json` | 테이블/자식별 exact count·서명 및 날짜별 품질/합계 |
| `expected-signatures.json` | 다섯 논리 테이블의 `{rows,sum_hi,sum_lo}` |
| `source-validation-manifest.json` | 같은 snapshot의 원본 검증값과 archive manifest를 SHA로 연결 |
| `status.json`, `status-fallback/`, `result.json`, `launcher.json`, 각종 로그 | PID, 시간, 진행/최종 상태, 오류 |

PVS는 자식별로 한 번 읽어 의존 수 합계·0·음수·NULL 수를 계산한다.
`package_snapshot`은 날짜마다 반복 스캔하지 않고 한 번의 GROUP BY로 날짜별 건수·다운로드 합계·NULL 수를 계산한다.
두 MD5 부분합은 행 순서에 영향을 받지 않는 확률적 무결성 검사다. 해시 충돌 가능성이 없는 완전 동일성 증명이라고 부르지 않는다.

## 중단과 실패 경계

`STOP_AFTER_CURRENT` 파일을 실행 폴더에 만들면 검증 중 현재 작업들이 끝나는 지점에서 실패 상태로 종료한다.
이 신호는 실행 중인 pg_dump나 긴 단일 SELECT를 즉시 멈추는 기능이 아니다.
export 세션이 끝나거나 컴퓨터/DB가 재시작되면 이전 token을 다시 사용할 수 없다.
이미 만든 파일은 조사용으로 남기고 새 폴더/새 기준 시점에서 실행해야 한다.

## 실행 전 검증

격리된 1GiB PostgreSQL에서 다음을 확인했다.

- 스냅샷 고정 뒤 package에 1행 추가: 현재 원본은 4행, 공유 snapshot 검증과 그 덤프의 복원 결과는 모두 3행.
- 실행기 전체 흐름: 3개 파티션 표본에서 `M3_COMPLETE` 도달.
- 날짜별/자식별 서명을 합친 결과가 다섯 테이블 직접 전수 서명과 일치.
- 단위 시험 20개 통과. 누락된 root/child 데이터, 부모의 잘못된 data 항목, 오래된 결과 폴더 재사용을 차단.

증거: `data/service-data-migration/m3-smoke/full-regression/regression-result.json`,
`m3-smoke/full-execution/status.json`, `m3-smoke/full-execution/aggregate-comparison.json`.

## 최초 실패 원인과 재실행

첫 실행은 덤프와 archive 검사를 306.078초에 완료했다. 이후 원본 검증 233개 중 199개를 마친 시점에
`status.json.tmp`를 `status.json`으로 교체하는 `os.replace`가 `PermissionError [WinError 5]`로 실패했다.
전체 경과 2,831.671초(약 47분 12초)에 실패 처리됐다. DB 계산 오류나 데이터 불일치가 보고된 것은 아니다.
접근을 거부하게 만든 구체적인 프로그램은 확인되지 않았다. 당시 구현이 일시적인 상태 기록 오류까지 전체 계산 실패로 전파한 것이 문제였다.

수정 내용:

- PID/UUID가 포함된 고유 임시 파일에 기록하고 원자적으로 교체한다.
- Windows 오류 5/32/33에 한해 짧은 지수 backoff로 최대 8회 시도한다.
- 상태 기록이 실패하면 별도 파일에 상태를 보존하며 계산을 계속한다. 상태 파일과 fallback을 모두 기록할 수 없으면 stderr에 경고를 남긴다.
- archive/receipt/검증 manifest 같은 필수 결과물 저장 실패는 계속 실패 처리한다.
- 최종 상태는 별도 `result.json`에 남긴다.

실제 Windows 파일 핸들로 삭제/교체 공유를 막은 상태에서 격리 DB 전체 실행이 `M3_COMPLETE`로 끝나는 것을 확인했다.
반대로 receipt 저장 실패를 주입하면 `FAILED`, `ready_for_transfer=false`를 유지했다. 단위 시험 23개 통과.
증거는 `m3-smoke/full-locked-status/`와 `m3-smoke/full-durable-write-failure/`에 보존한다.

첫 덤프 234개 파일, 10,233,114,532바이트의 SHA를 재검사해 모두 일치했다.
199개 receipt도 이전 snapshot을 가리킨다. 그러나 export 보관 세션이 이미 종료돼 남은 검증을 같은 token으로 수행할 수 없다.
이전 결과를 새 시점의 결과로 바꿔 표시하지 않고, 기존 파일을 보존한 채 새 덤프와 검증을 시작했다.
