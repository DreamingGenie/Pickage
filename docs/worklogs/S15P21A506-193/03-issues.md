# 03. 이슈와 해결 기록

상태: **입력 원본 위치를 확인했다. 정상 입력 승인과 전체 target 모집단 검증은 아직 미충족이다.** [계획](02-plan.md) · [결정](06-decisions.md)

해결 방향은 계획이다. 실제 조치·재검증 증거가 생기면 해당 이슈에 날짜와 결과를 추가한다.

| ID | 확인한 문제 또는 제약 | 영향 | 해결 방향·다음 확인 | 현재 상태 / 해결 결과 |
| --- | --- | --- | --- | --- |
| ISS-001 | 7번 기록이 `PARTIAL`, `ready_for_dependents=false` | 현재 계약으로는 정상 dependents 값의 서비스 게시 조건 미충족 | 입력·품질·사용 목적을 확인하고 기존 게시 차단 유지. 별도 진단용 계산이나 계약 변경 여부는 D-07에 기록 | 미해결 / 8번 입력으로 승인하지 않음 |
| ISS-002 | 7번 기록상 최종 `run_manifest.json`·`_SUCCESS` 부재, 별도 전체 행 검증은 메모리 부족으로 중단 | 정상 완료 run을 가정하는 입력 검증을 통과했다고 할 수 없음 | 파일·계보와 검증 가능 범위를 다시 확인하고 실행 자원·검증 방법을 정함. 완료 기록을 임의로 만들지 않음 | 미해결 / 이번에 전수 검증 재실행하지 않음 |
| ISS-003 | 현재 워크스페이스에 `data/requirements-resolution` 폴더가 없음 | 8번에서 사용할 입력 경로 확인 필요 | 기존 7번 run 위치를 읽기 전용으로 참조. 작은 메타데이터 해시·파일 목록·대표 스키마 확인 | 위치 확인 완료 / 이동·복사 없음. 전체 데이터 승인과 별개 |
| ISS-004 | prerelease 후보를 전부 제거하므로 명시적 prerelease 요구도 미해석될 수 있음. 정책 제외와 본래 만족 후보 부재가 선언 상태에서 구분되지 않음 | 일반 npm 매칭과 차이가 있으며 누락 관계의 사유 해석에 한계 | 기존 안정 버전 정책과 상태 분류 문제를 분리해 판단. 대상 정책·코드 변경은 별도 결정 기록 필요 | 확인된 기존 한계 / 코드 미수정 |
| ISS-005 | alias가 `UNSUPPORTED_ALIAS`이며 bridge와 최종 target 연결이 `declared_name` 기준 | 로컬에 실제 대상 후보가 있어도 별칭 관계를 계산하지 못함 | 별칭·실제 이름을 함께 보존하는 별도 설계 필요. 8번 집계에서 임의로 target을 추정하지 않음 | 확인된 기존 한계 / 코드 미수정 |
| ISS-006 | npa의 `EUNSUPPORTEDPROTOCOL`을 `INVALID_SPEC`으로 합침 | 미지원 프로토콜과 잘못된 선언의 품질 사유가 섞임. 해당 항목의 현재 RESOLVED 여부에는 영향 없음 | 오류 코드와 상태 분류의 변경 여부를 별도로 판단 | 확인된 기존 한계 / 코드 미수정 |
| ISS-007 | 서비스 count는 `INT NOT NULL DEFAULT 0`, 상태 컬럼 없음 | 미계산·미해석을 NULL로 넣거나 기본값 0으로 숨길 수 없음 | 계산 핵심에 PARTIAL 차단·INT 변환 전 범위 검사를 구현. DB 적재 전 검증은 후속 | 소형 집계 검증 완료 / 서비스 DDL 유지·DB 적재 미구현 |
| ISS-008 | 7번 prepare candidates 전체에 stable-semver 검사가 적용된 것은 아님. target_quality도 조회 패키지 한정 | candidates 또는 edge target만으로 전체 승인 target 목록을 만들면 0 부여 기준이 틀릴 수 있음 | 전체 후보에 기존 target 정책을 적용하고 검증한 모집단과 제외 증거가 필요 | 미해결 / 실제 전체 target 파일·행 수 미확정 |
| ISS-009 | 집계 핵심 초안이 배포일을 DATE로 비교하여 같은 날짜 안의 미래 배포를 구분하지 못함 | 정확한 snapshot 시각 계약 위반 가능 | published_at을 TIMESTAMPTZ로 제한하고 UTC 기준 날짜 일치·정확한 시각 비교로 수정 | 해결 — 같은 시각 허용·1마이크로초 이후 거부·동일 instant 타임존 변환 테스트 통과 |
| ISS-010 | 집계 핵심 초안의 결과 교체와 임시 집계 보존 | 기존 결과 덮어쓰기·실패 시 중간 결과·중복 저장 위험 | 기존 결과 거부, 계산·범위 검사·결과 생성·임시 집계 제거를 트랜잭션으로 묶음 | 해결 — 결과 생성 오류 주입 시 롤백·입력 보존, 성공 시 임시 테이블 제거 테스트 통과 |

## 근거와 해석 범위

- ISS-001: [7번 finalize 결과 기록](../S15P21A506-283/evidence/full-run-finalize.json), [현재 소비 계약](../../../pipeline/requirements_resolution/README.md).
- ISS-002: [7번 계산 결과](../S15P21A506-283/06-computation-results.md), [검증 중단 기록](../S15P21A506-283/08-verification-result.md). 선행 기록을 읽었으며 이번 문서 준비에서 원본 전체 파일을 재검증한 것은 아니다.
- ISS-003·008: [실제 입력 조사](07-input-contract.md), [작은 메타데이터·파일 목록 확인 증거](evidence/input-assessment.json). 폴더 부재가 산출물 전체 부재를 뜻하지 않는다.
- ISS-004~006: [Node 해석 구현](../../../pipeline/requirements_resolution/semver_worker.cjs), [bridge](../../../pipeline/requirements_resolution/bridge.py), [최종 target 연결](../../../pipeline/requirements_resolution/transform.py). 같은 대화의 선행 읽기 전용 재현 결과이며, 이번 문서 생성 단계에서 재현을 다시 실행하지 않았다.
- ISS-007: [서비스 DDL](../../../backend/src/main/resources/db/migration/V1__init.sql).
- ISS-009~010: [집계 핵심](../../../pipeline/version_dependents/aggregate.py), [테스트](../../../pipeline/version_dependents/test_aggregate.py), [최종 검증 증거](evidence/kernel-validation.json).

선행 기록의 `NO_ELIGIBLE_TARGET=7`만으로 7건 모두가 prerelease만 발행한 패키지 때문이라고 판단하지 않는다. 그 원인의 전수 분류는 미확인이다. alias 미지원 건수가 향후 모두 RESOLVED로 바뀐다고 가정하지 않는다.

## 새 이슈를 추가할 때

`발견일 / 재현 조건 / 기대 동작 / 실제 동작 / 영향 / 연결 결정 / 조치 / 검증 증거 / 최종 상태`를 기록한다. 증상만으로 원인을 확정하지 않는다.
