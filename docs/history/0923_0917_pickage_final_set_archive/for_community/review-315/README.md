# Phase 1~4 전반 검수 및 Phase 5 수정

## 기준과 승인

- 사용자 승인: 2026-09-11, 전반 검수→발견 결함 Phase 5 수정 계획에 “진행해줘”.
- 최초 코드: `d9193a3744c904963ad13c8c710f0548a9ab8437` (317, Phase 1~4 포함).
- 통합 비교: `origin/develop@8372b17b90c91bc80a1b6ebbdf90e0eb2ff69af4`.
- 작업: `api/fix/S15P21A506-315-community-integration-acceptance`.
- 선행 317의 미병합 코드를 포함해야 하므로 Phase 인덱스의 선행 브랜치 기반 예외를 적용. 헬퍼가 origin/develop으로 고정되어 있어 직접 분기함. 기존 브랜치와 Jira 212/317 상태는 보존.
- 기획 목적·요구사항: 현행 0910 요구사항/IA/개발 구상안, 커뮤니티 구현계획 §1~12. 사용자 확정 결정은 관련 Spec §7과 완료 기록에서 대조. 완료 기록의 통과 선언은 검증 증거와 구분.
- Jira 완료 기준은 [315](https://ssafy.atlassian.net/browse/S15P21A506-315)의 완료 판단 기준이 정본. 이 문서는 추적표이며 기준을 대체하지 않음.

## 순서

기준선 → 요구사항/파일 추적 → 기획 적합성 → Phase 간 전달 → 기존 기능 통합 → 계약/실패/자원 → 반례 재현 → 수정 → 재검증 → 사람 최종 검토.

## 체크포인트

- 제출: [Draft MR !117](https://lab.ssafy.com/s15-bigdata-dist-sub1/S15P21A506/-/merge_requests/117), 315 → develop, 리뷰어 jungbk0808, backend/fix/docs. 충돌 없음. 생성 후 조회 시 CI pipeline은 없으며 로컬 검증과 구분한다. Jira315는 외부 인수·사람 리뷰를 위해 진행 중으로 유지했다.
- 사용자 승인: “phase 5 개발하고, 커밋한 후, 전체 재검수 진행한 후에 문제 없다면 mr까지 넣어줘”. 공용 seed 4개와 PdfStoreTest 호출 2곳 보정 포함.
- Phase 5 구현: API/저장 계약 v2, 검증·수집·요약 근거, 제한 실행과 게시, 비활성 격리, seed FK 수정. [수정 대장](remediation.md)을 기준으로 추적한다.
- 수정 전 38개 반례(35 실패/3 통과)와 d9193a3 파일 목록은 보존했다. `probes/`는 당시 코드에서만 실행한다. 현재 코드는 정규 test/integrationTest 소스에 이관한 회귀 시험을 실행한다.
- 구현 `d264a3a`, develop 통합 `4e57ab1`, 재검수 보정 `8f43632`·`ce4dd91`. 단위 243 통과·DB/앱 33 통과(실외부 opt-in 3 skipped), frontend typecheck/build 통과. [전체 재검수](final-review.md)·[수정 후 증거](evidence/post-fix-results.json)를 확인한다.
- FE316 신규 탭·C1 실 GMS/prompt/의미 평가·C6 운영 자원/secret gate는 확인 필요(외부 의존성). 현재 fake는 실제 topic을 성공으로 꾸미지 않으며, 새 refresh는 readiness가 갖춰져야 시작한다.
- Jira315 진행 중. 선행 212/317 상태와 원격 브랜치를 보존한다. 최종 검증 커밋·명령은 별도 검수 기록에 남겼다. Draft MR에서 사람 리뷰와 외부 인수를 추적한다.

## 기록 규칙

발견 ID → 요구사항 원문 → 재현 조건 → 기대/실제 → 영향 → 코드/시험 증거 → 수정 파일 → 재검증. 확정 결함/의심/승인된 절충/외부 의존/기존 무관 결함을 구분. 작업 재개 시 이 파일과 git status를 먼저 읽는다. 완료되지 않은 항목은 통과로 바꾸지 않는다.
