# 요구사항 추적표

원문: `../Pickage_GitHub커뮤니티_구현계획_260908.md`, `../../Pickage_요구사항_명세서_0910.md` 확장-03. 미검증은 결함 확정이나 통과가 아니다.

| ID | 원문·목적 | 연결 구현 | 필수 증거 | 상태 |
|---|---|---|---|---|
| R01 | R01/R13/R14, §1/3.1 기준 하나·검증·대체 금지 | PackageLookup, verification, repository DTO | npm/DB 결정표·SSRF·private·directory | F13/F14 실패 재현·정적 근거; 수정 필요 |
| R02 | R02/R03/R11, §3.2/6 같은 topics 집계 | collection→payload→Service | 원천 수치·부분 결과·snapshot 일치 | 동일 topics 합산 경로 확인; wire/요약 상태 F01/F04 수정 필요 |
| R03 | R04/R05/R16, §3.2 선정 범위 | SearchClient/SelectionPolicy | raw0/incomplete0/필터0/365일 | F15 incomplete0 재현, 기간/한계 손실 확인 |
| R04 | R07/R08/R16, §3.3 댓글 윈도 | CommentsClient/WindowResolver | 0/100/101/199/200/301·중복·변경·큰ID | F16 101·정렬 반례 실패; 변경/page 조합 보완 후 재검증 |
| R05 | R06/R09/R10, §4 요약 근거·역할 | Summarizer/TopicSummary/payload | 지원 source·Bot·null author·부분/전체 실패 | F04 실패 재현/F17 근거 누락 확인; C1 의미 평가 미실시 |
| R06 | R10/R11/R12, §5.1 저장·복원 | Repository/payload/V5 | source·policy·365일·unsupported/손상 | F05 실제 DB 실패/F15/F17 보완; 새 app 재시작 전체 fixture는 수정 후 |
| R07 | R17, §5 TTL·재시도 | Ttl/Service/registry | 24h/7d/완료+5분·외부 gate | F04/F06/F07 반례 실패 |
| R08 | R18, §6 API·상태 | Controller/Service/dto | 전체 key·null·enum·시각·에러·no-store | F01~F03 실패, F20 정적 확인; 실제 snake_case/null은 통과 |
| R09 | R18, §7 제한 실행 | coordinator/task/registry | 50중복/50패키지·포화·대기/실행·shutdown | F09/F10 5개 반례 실패; 50개 부하/종료 전체 시험 미실시 |
| R10 | §3.4/7/10 외부 I/O·로그 | HTTP clients/reader/orchestrator | body stall·byte cap·rate 공유·로그 정제 | F11 local HTTP 실패/F08/F18 정적 확인; 로그 sentinel 재검증 필요 |
| R11 | R11/R17, §5.3/9 원자 게시 | orchestrator/Repository | connection/lock/statement·rollback·늦은 게시 | F12 실패; 실제 rollback 통과; connection/lock 지연 미실시 |
| R12 | §9/10 기존 기능 독립 | Config/global/package/report | 실제 Spring 직렬화·기동·기존 API 회귀 | 실제 기동/검색/직렬화 통과; 통합 build는 report 시험 제외; F20 수정 필요 |
| R13 | R01/R18, §8 FE | api client/report shell | route·mock·탭 필터·숨김 polling | 정적 경로 확인·통합 typecheck/build 통과; 신규 FE316 및 browser E2E 미실시 |
| R14 | §9/10/12 운영 | migration/seed/env | 빈DB/upgrade·seed4·실연결·메모리 | 기존 DB15 통과; F19 seed TRUNCATE 실제 실패; seed 전체 실행/C6 운영 미실시 |
| R15 | R15 Activity 시계열 | ecosystem | community 배치 시계열 추가 없음 | 적용 제외(다른 기능) |

## 종료 조건

모든 행과 파일 목록에 최종 판정·증거/제약을 남긴다. 확정 결함은 발견 대장의 수정/재검증과 연결한다. FE·외부 미연결을 backend 시험 통과로 대체하지 않는다.

현재 판정은 **수정 전 검수**다. F 번호는 [발견 대장](findings.md), 시험 메서드별 결과는 [evidence](evidence/probe-results.json), 정확한 재현 명령과 baseline 제외 항목은 [검증 기록](evidence/README.md)을 따른다. 단위/DB 반례가 커버하지 않은 전체 인수 조합은 위 상태 열과 Spec §5에 남겼다.
