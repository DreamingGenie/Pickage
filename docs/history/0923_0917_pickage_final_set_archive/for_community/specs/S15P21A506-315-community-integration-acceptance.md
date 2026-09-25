# Phase 5 Spec — 커뮤니티 계약·통합 결함 수정과 재검증

## 0. 대상 Phase

- Jira: [S15P21A506-315](https://ssafy.atlassian.net/browse/S15P21A506-315).
- 브랜치: `api/fix/S15P21A506-315-community-integration-acceptance`, base `d9193a3`(317 포함). 선행 미병합 코드를 잃지 않도록 Phase 인덱스의 분기 예외 적용.
- 구현계획: [원문](../Pickage_GitHub커뮤니티_구현계획_260908.md) §3~7/9~12. 현행 기획은 docs/의 0910 문서 세트.
- 선행: Phase 1~4, 사용자가 완료·push 상태를 알리고 이들 전체의 검수 및 Phase 5 결함 수정을 지시함.
- 현황: 세부 Spec 승인 후 Phase 5 구현·단위/격리 DB 시험 진행. 커밋 후 최신 develop 통합 재검수와 조건부 MR까지 승인받음. review 산출물은 [검수 결과](../review-315/findings.md) 참조.

## 1. 작업 개요

목표는 개발된 부품을 기획 목적에 맞는 하나의 동작으로 연결하고, 발견된 계약/실패/자원/기존 seed 회귀를 해결하는 것이다. F01~F20을 Phase 5 수정 단위로 사용한다. 스타일 일괄 정리나 다른 기능 재설계는 포함하지 않는다.

Jira의 필요한 이유·영향 범위 원문:

> QA 역할(기획 교차 검수 + BE/FE 구현 담당). 250은 상태 대응표 검수이고 본 이슈는 lifecycle/자원/재시작 통합 반례를 소유한다. 인프라 실행이나 AI 모델/prompt 수정 작업을 재배정하지 않는다.

Jira **완료 판단 기준** 원문(새 AC 아님):

- [ ] 문서 §12 요구별 명령·fixture·결과·화면 증거가 추적된다.
- [ ] BE/FE/DB 기능 gate와 외부 C1/C6 gate를 분리하고 미실시 시험을 통과로 표시하지 않는다.
- [ ] 이전 정상 생태계·기능 비교가 community key 누락·장애·탭 왕복으로 회귀하지 않는다.

사용자의 추가 지시인 ‘발견 문제를 Phase 5에서 해결’에 따라 검증뿐 아니라 아래 범위의 결함 수정까지 수행한다. 기존 Jira212/317의 담당·상태·AC를 덮어쓰지 않는다.

## 2. 변경 대상 (Scope)

실제 파일을 확인한 [수정 파일 목록](../review-315/scope.md)을 이 Spec의 일부로 사용한다. 파일 목록 밖 변경이 필요하면 이유와 구체적 범위를 먼저 제시한다.

| 묶음 | 목적 | 연결 결함 |
|---|---|---|
| 공개 DTO·상태·오류·Swagger·nullable 전체 fixture | §6 필수 key와 enum, 결과 우선, 최초 IDLE, no-store | F01~F04 |
| payload·검증·저장·TTL | v2·정책 식별·source 근거·실제 기간·미지원/손상·재시작 | F05~F06/F12/F15/F17 |
| repository 검증·검색·댓글 | public/연결 판정·fallback 차단·범위/한계·수집 순서 | F13~F17 |
| admission·registry·task·외부 I/O·게시 | 원자 상한·재시도·deadline·취소·전역 rate·정제 | F07~F12/F18/F20 |
| 격리 통합 시험·공용 seed 최소 보정·빌드 기준선 보정 | 실제 기능 회귀와 인수 증거 | F19 및 기존 시험 장애 |

공유 범위의 구체적 추가 변경 제안:

1. `deploy/local/seed/seed_sample.sql`, `seed_mock_parity.sql`, `seed_service_full.sql`, `seed_reset.sql`의 기존 TRUNCATE 목록에 `community_snapshot`만 추가. 인프라 담당 경계이지만 V5로 이미 깨진 기존 초기화를 복구하기 위해 필요하다. `seed_clear_snapshots.sql`은 변경하지 않는다. 개발 DB에서 실행하지 않는다.
2. `backend/src/test/java/com/ssafy/pickage/domain/report/PdfStoreTest.java`의 save 호출 2곳에 현행 시그니처의 html fixture 인자를 추가. 제품 report 코드는 변경하지 않는다. 기존 무관 오류를 커뮤니티 수정 성과로 세지 않으며, 시험 제외 없이 전체 build를 실행하기 위한 최소 보정으로 분리한다.

Jira 제외 범위: “기능 비교 RAG AI나 커뮤니티 GMS prompt를 변경하지 않는다.” 인프라 실행·AI 모델/prompt 업무를 재배정하지 않는다. frontend316 신규 화면·실제 GMS method/path/auth/model·환경 secret/compose/application.yaml은 이번 구현으로 임의 결정하지 않는다. C1/C6은 확인 필요(외부 의존성)다.

## 3. 아키텍처 / 데이터 흐름

### 3.1 계약과 저장 형식을 먼저 고정

§6 필드 사전을 그대로 JSON fixture로 만들고 Controller의 Swagger 응답·오류 설명을 맞춘다. 기존 wrapper/snake_case를 재사용한다. Spring 실제 converter로 필수 nullable key까지 검사한다. 공개 DTO에서 source ID/support 목록을 제외한다.

payload v2는 repository/topics/limitations와 policy_version=`github-active-v1`, 실제 lookback, summary_retry_at, 내부 source_issue_id/source_comment_id/association/검증된 is_issue_author를 보존한다. v1에는 created_at·source 근거 등이 없어 무손실 변환을 할 수 없으므로 결과 없음으로 처리하고 다음 POST에서 재수집한다. 이 때문에 기존 v1 캐시가 재사용되지 않는 영향은 문서화한다. V5의 JSONB와 positive payload_version 제약으로 수용 가능하여 **기존 migration 수정이나 새 migration은 계획하지 않는다**.

읽기·쓰기에서 필수 key/enum/상한/UTC시각/십진ID/source 관계를 검증한다. 미지원 버전은 재수집 자격, 지원 버전 손상은 S001과 정제 로그다. TTL은 `[0,24h)` fresh, `[24h,7d)` stale, 7d 이상 비노출. 조회 시 합계는 동일 topics의 원천 수치로 계산한다.

### 3.2 검증된 repository에서 근거를 잃지 않고 수집

npm absent/invalid/unsupported를 구별하고 latest name·public metadata·directory 안전성·workspaces·DB-only 결정을 검증한다. 기존 fixed host/redirect 차단을 유지한다. 충돌/heuristic/범위 한계는 구조화된 limitation으로 인계한다.

complete raw0만 180→365 확장하고 실제 lookback을 보존한다. incomplete0/필터0의 한계를 잃지 않는다. 댓글은 first→last→필요한 previous 순서로 최대 3회, 중복 제거 후 created_at·numeric ID 기준 최신 100개. 절단·변경·부분 실패를 드러낸다. issue body/created_at/source ID와 stable author 근거는 refresh 메모리에만 유지한다.

### 3.3 요약 경계와 집계

C1 실제 프로토콜은 fake로 남기되 BE의 bounded executor(전역 2 threads/queue2)·남은 예산 future 대기·취소·구조와 source 근거 검증을 마련한다. 원문 §4의 개별 4,000자/전체 48,000자(Unicode code point) 상한을 적용한다. 모델이 임의로 보낸 login/role/source를 그대로 신뢰하지 않고 수집 근거로 복원한다.

topic이 없을 때만 SKIPPED, 일부 성공은 PARTIAL, 전체 실패에만 실패 확정+5분을 기록한다. 사실 수치는 요약 실패와 분리한다. 실제 모델 의미 평가·사람 평가를 fake 통과로 대체하지 않는다.

### 3.4 admission과 실행 수명

package 존재 → 동일 active 참여 → fresh/summary 및 최근 실패 재사용·retry 자격 → readiness → 전역 rate → 원자적인 registry/permit/queue/token 결정. 최종 수락 구역에서 동일 package와 재사용 결과를 재확인한다. 새로 수락한 작업에만 token을 소비하고 거절을 영구 registry에 남기지 않는다.

registry128, worker2, queue4; queue20초와 worker 시작 후20초를 분리하고 started_at은 실제 시작 전 null. 종료 전이는 되돌릴 수 없다. 독립 만료 감시가 stalled worker와 무관하게 queued task를 끝내고 실행 취소를 요청한다. 조회 중 종료 TTL10분 정리, shutdown은 새 admission 차단→5초 grace→queued/running 취소·자원 회수다.

GitHub core/search gate를 client 전역으로 주입한다. primary/secondary/Retry-After/reset 및 잘못된 헤더를 정제해 처리하고 최근 실패+5분보다 늦은 제한을 우선한다. HTTP는 header부터 body 완료까지 하나의 deadline·decoded byte 제한을 적용하고 취소 시 스트림을 닫는다. 별도 무제한 thread/queue로 timeout을 흉내 내지 않는다.

readiness는 community 내부 abstraction으로 두며 enabled 기본 false와 외부 의존성 준비 여부를 판단한다. 기존 사용자 결정대로 상한은 상수 클래스에 유지한다. secret을 공용 설정 파일에 새로 쓰지 않고 core startup/fresh/active 동작을 보존한다.

### 3.5 게시와 이전 결과 보존

worker 시작 시 collected_at을 고정한다. 실행 마지막 2초를 예약하고 수집/요약에는 앞쪽 예산만 제공한다. 게시자는 같은 DataSource로 남은 시간 내 connection을 확보하고 동일 transaction 안에서 lock 최대1초/statement 최대2초를 남은 예산으로 줄인다. 무제한 connection 대기 작업을 쌓지 않으며 취소 후 늦게 얻은 connection도 닫는다.

task ID/active 소유권/deadline을 게시 시작과 commit 직전에 검사하고 terminal/취소 작업은 저장하지 않는다. task 상태 전이와 게시 권한을 하나의 명시적 동기화 규칙으로 연결한다. 실패는 rollback하며 이전 snapshot은 보존한다. DB commit 완료 후에만 COMPLETED로 표시한다.

## 4. 예외 및 엣지 케이스

Jira 세부 항목별 수행:

| Jira 세부 항목 | 구현·검증 연결 |
|---|---|
| repo/검색/101·199·301·큰ID·부분 실패를 API→DB→FE 연결 | F13~F17 fixture를 실제 controller/DB로 연결; FE316 미확보 단계는 미통과 |
| 단일 실행·포화·거절 GET·취소 게시·connection/lock·이전 결과 | F02/F09~F12 deterministic barrier·latch·격리 DB 시험 |
| 24h/7d·완료+5분·365일·역할·unsupported·손상·재시작 | F04~F07/F15/F17 저장 후 새 app context/registry로 조회 |
| 수치 분모·원문/요약·자료/요약 실패·원문 비저장·로그 정제 | F01/F04/F17/F18 source fixture와 DB/wire/log sentinel |
| AI/prompt 제외·외부 인수 자료 확인 | C1/C6 자료 확보 전 확인 필요(외부 의존성) |
| mock/실DB/실외부 구분 | evidence 결과표의 gate를 독립 관리 |

완료 판정을 흐리는 항목은 숨기지 않는다: unsupported v1 재수집 영향, GMS 미연결, FE 미구현, 운영 connection/메모리 환경 차이. 새 기술 선택이 필요한 경우 실제 경로/상한과 영향이 이 Spec 안에 들어오는지 먼저 대조한다.

## 5. 검증 계획

1. 먼저 확정 반례를 정규 test/integrationTest로 옮기고 원문과 어긋난 기존 기대값은 근거를 적어 교체한다. 모든 기존 시험을 삭제하거나 실패를 ignore하지 않는다.
2. Clock·latch·barrier로 TTL/상태/소유권을 검증한다. 실HTTP body timeout은 loopback 서버, 실제 DB는 DisposableTestDatabase만 사용한다.
3. 같은 package50개/서로 다른 package50개, registry 경계·burst·queue·pool 상한·늦은 future·shutdown를 검사한다. 게시용 connection/lock 지연 후 예산·rollback·worker 회복을 확인한다.
4. raw sentinel/토큰 모양 fake 문자열을 client 예외에 넣고 DB/wire/log에서 미노출을 확인한다. 실제 secret/실저장소 원문을 fixture로 사용하지 않는다.
5. 공용 seed4개 전체는 disposable DB에서 각각 실행. latest develop 통합본에서 backend build·frontend typecheck/build 및 가능한 기존 API 회귀를 재확인한다.

수정 후 명령(backend에서):

```powershell
.\gradlew.bat test build --console=plain
.\gradlew.bat integrationTest --tests '*Community*IntegrationTest' --console=plain
```

새 인수 통합 시험 클래스는 `CommunityAcceptanceIntegrationTest`로 만들고 위 패턴에 포함한다. 실제 GitHub 네트워크 테스트는 위 패턴으로 실행하지 않는다. frontend에서는 `npm.cmd run typecheck`, `npm.cmd run build`; 브라우저의 community 탭 왕복은 FE316 인계 후 별도 실행한다.

AC 매핑:

- 첫 AC: R01~R15→F01~F20→정규 fixture/명령/결과 연결. 화면 미실시는 증거 없음으로 기록.
- 두 번째 AC: BE(mock)/DB(real)/FE(browser)/C1/C6 표를 따로 두고 연결 대기를 통과로 바꾸지 않음.
- 세 번째 AC: 기존 검색·생태계·기능 비교 API·FE 회귀 및 community 오류·키 누락·탭 왕복 증거 필요. 현재 typecheck/build만으로 완료 체크하지 않음.

## 6. 자체 검증

- 실제 community main/test/integrationTest 101개 파일을 inventory로 고정. source hash는 기준 commit과 대조용이다. 수정 파일과 신규 예정 파일은 [scope](../review-315/scope.md)에서 별도로 구분했다.
- `PackageNames.isValidName`은 `domain/packages/PackageNames.java`의 public static이며 재사용 가능. global/util 경로가 아님을 실제 파일로 확인했다.
- 실제 Boot app converter가 snake_case/null을 내보내는 것은 통과. 수동 mapper 설정 변경이 아니라 DTO 계약을 고쳐야 함을 반영했다.
- V5는 이미 병합·적용된 JSONB 스키마다. 수정 금지, 새 payload 버전만으로 수용 가능함을 확인했다.
- seed 실제 대상은 harness의 ‘세 파일’보다 많은 **4개**다. seed_reset을 포함해야 하며 seed_clear_snapshots는 별도 의미다.
- backend 전체 시험의 독립 장애는 PdfStoreTest 호출 2곳임을 확인했다. frontend setError는 최신 develop에서 해소되어 별도 수정 대상에서 제외했다.
- 213의 JDK HttpClient/2MiB, 317의 상수 클래스·인메모리 registry 선택은 유지한다. 실제 GMS/외부 환경 값을 추측해 추가하지 않는다.
- 남은 사용자 결정: 이 구체적 수정 Spec과 공용 seed4개·기존 PdfStoreTest 최소 보정을 Phase5 범위에 포함할지. 외부 C1/C6/FE의 미완료를 구현 완료로 바꾸지 않는다.

---
세부 Spec 승인: 2026-09-11, 오세진 — “phase 5 개발하고, 커밋한 후, 전체 재검수 진행한 후에 문제 없다면 mr까지 넣어줘”. 제시한 공용 seed4곳/PdfStoreTest 호출2곳 보정 포함. 커밋·재검수·조건부 MR 진행까지 승인받았다. FE/C1/C6 외부 gate를 실제 통과로 바꾸는 승인은 아니다.
