# Phase 5 수정 대장

수정 전 근거는 [F01~F20](findings.md)에 보존했다. 아래는 BE의 수정·검증 범위이며 FE/C1/C6 인수 통과를 뜻하지 않는다.

| 발견 | 반영한 수정 | 정규 회귀 증거 |
|---|---|---|
| F01 | §6 DTO와 source를 보존하는 payload v2, 같은 topics 집계 | CommunityContractReviewTest, 실제 앱 전체 result.json 비교 |
| F02 | IDLE/null, RESULT 우선, RUNNING stage, queued started_at=null | Service/Contract/Concurrency 시험 |
| F03 | PackageNames 검증, 두 경로 오류까지 no-store | 실제 앱 V001/V004/누락/S001 시험 |
| F04 | READY/PARTIAL/FAILED 집계, 전체 실패만 재시도, 자료 상태 분리 | Orchestrator/Contract 시험 |
| F05 | 버전 무시와 지원 버전 손상 오류 분리, JSON 필드·타입/typed 검증 | Repository/Acceptance 실제 DB 시험 |
| F06 | 정확히 24h stale, 7d 비노출, 정리 <= | TTL/Contract 시험 |
| F07 | 최근 실패·snapshot·외부 retry 최댓값, 수락 전 판정 | Service/Orchestrator/Contract 시험 |
| F08 | 공용 core/search/secondary gate, 성공의 remaining=0 반영 | VerificationContractReviewTest와 client 시험 |
| F09 | admission 원자화, token 사전 판정/반환, DB는 registry 잠금 밖 | 50 동일·50 별개·128 경계, prefetch token 시험 |
| F10 | queue/run 기한 분리, 별도 만료 감시, 취소·종료·terminal 불변 | ConcurrencyContractReviewTest, 기존 coordinator 시험 |
| F11 | body 완료까지 request deadline, 누적/압축 해제 byte cap | local HTTP stall 및 기존 client 크기 시험 |
| F12 | worker 시작 collected_at, 마지막 2초 게시, 소유권/transaction/lock 제한 | 실제 lock timeout·late connection close·취소·rollback·정상 재게시 |
| F13 | 잘못된 npm 연결의 DB fallback 차단, userinfo/경로 검증 | URL/Candidate/Npm/Verification 시험 |
| F14 | private 차단, workspaces/repo-wide·DB-only ambiguity·한계 보존 | Scope/Verification/client 시험 |
| F15 | complete raw0만 365 확장, incomplete0 PARTIAL, lookback 저장 | CollectionContract/IssueCollection 및 재시작365 시험 |
| F16 | first/last/조건부 previous, 최신100 선별 후 시각/큰ID순, 절단 명시 | WindowResolver/IssueCollection/CollectionContract 시험 |
| F17 | source ID/본문 전달, 4000/48000자, support 검증·작성자 복원, pool2/queue2 | 요약 위조·원문 예산·timeout/회복·payload/역할 시험; C1 의미 평가는 외부 |
| F18 | raw exception/body/URL 대신 refreshId/packageId/code 로그 | failure log sentinel 시험, 로그 호출 정적 검토 |
| F19 | seed 4곳 TRUNCATE에 community_snapshot 명시 | 격리 DB에서 SQL 4개 전체 실행·FK 있는 상태 반복 |
| F20 | readiness 미충족 시 새 refresh 차단, 조회·기존 기능 기동 유지 | Service 비활성, 실제 앱 기동/조회/검색, 전체 context 시험 |

예정된 보조 클래스 중 RepositoryMetadata/PackageJsonEvidence/RefreshDeadlineSupervisor는 따로 만들지 않았다. 기존 검증 결과 enum/record와 coordinator 내부 supervisor로 책임을 구현했다. public endpoint, 공유 설정, migration 번호를 늘리지 않았다.

실제 모델의 답변 정확성·유해 입력 평가, FE 커뮤니티 탭의 렌더링/polling/필터/탭 왕복, 운영의 메모리와 1vCPU 부하는 이 BE 시험으로 보증하지 않는다. 상세 최종 명령·결과는 커밋 후 검수에서 기록한다.
