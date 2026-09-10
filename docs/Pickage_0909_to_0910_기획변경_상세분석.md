# Pickage 0909→0910 기획변경 상세분석

작성 기준일: 2026-09-10
연결 결정: `DEC-DEPENDENCY-DELTA-20260910-01`, `DEC-ECOSYSTEM-INPAGE-EXT-20260910-01`, `DEC-API-ALIGN-20260910-01`, `DEC-SERVER-ALIGN-20260910-01`
유지 결정: `DEC-COMMUNITY-20260909-01`, `DEC-RANK-20260909-01`

이 문서는 2026-09-09 기획 세트(서비스 기획서·요구사항 명세서·메뉴구조 IA·기능별 개발 구상안)에서
2026-09-10 최종 재검수 세트로 바뀐 지점만 추적한다. 0910 변경은 단순 UI 문구 수정이 아니라
Dependency 데이터 의미 재정의, 개발팀 API 정본 반영, 실제 서버 사양 정합, 확장 기능의 화면 소유권
정리까지 포함한다. 0909의 후보 ranking 결정과 GitHub 커뮤니티 단일 패키지/Spring-GMS 한정 예외는
폐기하지 않고 유지했다.

## 검수 토론 후속 확정 — 2026-09-10 (`DEC-RECONCILIATION-20260910-01`)

정합성 검수 뒤 제품·개발팀과 다음을 확정했다. 이 절은 아래의 당시 변경 이력을 지우지 않고, 이후
후속 구현 계약과 Figma·0910 문서에 적용할 최종 해석을 기록한다.

1. **PDF 적격성**: 기능 비교의 패키지별 현재 선택 버전 결과가 완료되어야 PDF를 생성한다. 버전 변경 후 기존 결과는 보존하지만 PDF는 `BLOCKED`다. 따라서 PDF는 기능 비교가 제공되는 단계의 통합 산출물이며, 생태계 MVP 화면의 완료 조건과 구분한다.
2. **예시 기준 패키지**: 입력·후보 선택·보고서·PDF의 예시는 `pino → winston → bunyan` 순서로 통일한다.
3. **날짜 표기**: 관측 구간은 `2025.03.03–2026.08.31 · 78주 구간`, Version Share 기준일은 `2026.09.02`로 통일한다. `최근 78주`처럼 기준일이 흔들리는 표현은 쓰지 않는다.
4. **bunyan**: 자동 ranking 후보가 아니라 사용자가 수동으로 추가한 과거 비교 대상 예시다.
5. **근거 ID**: 한 ReportSnapshot 안에서 `package@version + sequence`가 하나의 근거를 가리킨다. 화면에는 `pino@10.3.1 · E01`처럼 보이고, 내부 복사값은 reportSnapshotId를 포함한다.
6. **Dependency signed delta**: 현행 코드대로 조회 구간의 첫·마지막 유효 관측값 차이로 표시한다. 바로 직전 Snapshot 계약은 철회한다.
7. **관측 공백**: 주간 수집에서 8일을 넘는 간격은 원인을 단정하지 않고 선을 끊어 연속 관측으로 오해하지 않게 한다.
8. **지표 실패 격리**: Dependents·Downloads 중 하나가 실패해도 정상 카드와 패키지 정보는 유지하며, 실패 카드 안에서만 재시도한다.
9. **입력 구현 경계**: 현행 sample registry는 시제품 데이터로 보존한다. 입력과 수동 추가는 자동완성 목록을 직접 선택해야 하며, 실제 연동 시에는 검색 결과의 선택 토큰과 후보 API로 교체한다.
10. **78주·로그축**: 프런트·백엔드 조회 상한을 78주로 맞추고, 0을 포함하는 `log1p` 로그축을 사용한다.
11. **Version Share 확장**: 사용자는 최신 완료 Snapshot 기준의 버전 분포를 본다. 이를 위해 원본 requirement·해석 상태·분모를 보존하는 전용 집계 산출물을 추가하며, 현 ERD는 확장 목표 설계로 존중한다.
12. **준비 상태**: 날짜가 snapshot 테이블에 있다는 사실만으로 자료 준비 완료로 추정하지 않는다. 지표별 완료 실행·기준일·자료 상태를 묶어 게시하고 PDF도 같은 ReportSnapshot을 고정한다.
13. **ERD 해석**: ERD는 개발팀이 합의한 최신 목표 설계다. 현재 코드·마이그레이션과의 차이는 오류가 아니라 이행 과제로 기록한다.
14. **유사 후보 저장**: ERD의 `similar_package`는 현재 서빙 결과 한 벌을 보관한다. 새 모델 결과는 staging 검증 후 원자 교체하고, 모델 버전과 검증 결과는 실행 manifest로 추적한다.

이번 기획 작업의 수정 대상은 요구사항·서비스 기획서·IA·개발 구상안·Figma다. 프런트·백엔드·데이터·배포 등 실제 구현 파일은 수정하지 않으며, 78주 상한·차트·입력·상태 처리 등 구현 필요사항은 WORKLOGS의 후속 목록으로 관리한다. API wire와 Version Share 확장 스키마는 개발팀 Notion/Swagger 반영 전까지 OPEN으로 남긴다.

## 결정 1 — Dependency 유지·유입·이탈을 MVP에서 제거하고 Snapshot signed 증감으로 전환 (`DEC-DEPENDENCY-DELTA-20260910-01`)

**무엇이 바뀌었나**: 0909 MVP는 Direct Dependency 카드 하단에서 `유지·유입·이탈`을 각각 계산해
보여주는 계약이었다. 개발팀이 실제 서빙 데이터는 Snapshot별 `dependents_count` 개수만 갖고 있고
동일 dependent의 식별자 집합을 보유하지 않는다고 확인하면서, 이 세 상태는 현재 데이터만으로 계산할
수 없는 기능으로 재분류했다.

0910 최종 계약은 같은 표시 필터(`Total` 또는 특정 version)와 현재 조회 구간에서 **첫 유효 관측값과
마지막 유효 관측값의 직접 의존 선언 수 차이만** signed 값으로 표시한다. 계산은 서버 summary가 아니라
프론트 `adapter.ts`가 trend point로 수행한다. `+N`은 총수 증가, `-N`은 총수 감소이며 유입/이탈을
뜻하지 않는다. 유효 관측값이 2개 미만이면 `0`으로 대체하지 않는다. `유지·유입·이탈` 자체는 기능-08
확장 검토로 이동했다.

**왜 바뀌었나**: aggregate count 두 개만으로는 동일 dependent가 계속 남았는지, 새로 들어왔는지,
사라졌는지를 식별할 수 없다. 가능한 상태 조합이 여러 개이므로 count 차이에서 identity flow를
역산하면 데이터가 말하지 않는 사실을 만들어내게 된다. MVP에서는 현재 데이터가 확실히 지원하는
순증감만 제공하고, identity-level 관계를 계산할 수 있는 파이프라인이 검증될 때 기능-08을 다시 연다.

| 문서 | 위치 | 0909 | 0910 |
|---|---|---|---|
| 서비스 기획서 | MVP 범위, §7.2, §7.6, PDF, MVP 완료범위 | 직접 의존 기준 유지·유입·이탈 | 조회 구간 첫−마지막 유효 관측 signed 총수 증감, 유지·유입·이탈은 확장 |
| 요구사항 명세서 | §9.1, 기존 §9.2, §13 PDF, 기능 연결 | 기능-08-R01~R04가 MVP 유지·유입·이탈 제공 | 기능-07이 delta를 소유, 기능-08은 확장 검토 |
| 메뉴구조 IA | §8.2~8.3, PDF 구조 | 하단 `유지·유입·이탈` 3종 지표 | 비교 패키지별 동일 signed delta 카드 |
| 기능별 개발 구상안 | §5.1~5.2, 저장/PDF/시험 | `summary{retained,inflow,outflow}` 등 묶음 계약 | server summary 삭제, adapter 조회 구간 첫·마지막 유효 관측 계산 |
| Figma | 화면03A/PDF/Requirement Map | 유지·유입·이탈 3카드·old Snapshot pair | package별 +/- 카드, 조회 구간 첫·마지막 유효 기준, old hidden frame 제거 |

**추가로 명확해진 것**: delta는 그래프에 표시된 조회 범위와 같은 trend에서 첫·마지막 유효 point를
사용한다. 별도의 직전 Snapshot을 숨겨서 가져오거나 새 endpoint를 임의로 만들지 않는다.

## 결정 2 — API 정본을 개발팀 Notion 명세로 올리고 UI/API 책임 경계 정리 (`DEC-API-ALIGN-20260910-01`)

**무엇이 바뀌었나**: 0909 개발 구상안에는 화면 요구와 API JSON 스케치가 섞여 있었다. 0910부터
endpoint·request·response wire·오류 코드는 개발팀 Notion API 명세를 canonical source로 두고,
서버 반영 뒤에는 Swagger를 실제 구현 최종 기준으로 사용한다.

함께 확정된 항목은 다음과 같다.

- Dependency 특정 version: `/packages/dependents`의 `version` query parameter
- Dependency delta: 프론트 `adapter.ts` 계산
- Downloads: weekly, 한 point는 직전 7일 합계, 최대 78주
- HTTP / `api/types`: snake_case, UI/domain camelCase는 adapter 경계에서만 변환
- 공통 `data_status`: `COMPLETE/PARTIAL/NO_DATA/COLLECTION_ERROR/CONFLICT/STALE`
- `relationship_type=DIRECT`: MVP Dependency 범위를 명시하는 metadata 요구
- 후보 ranking API: 임베딩 모델 실결과 확인 전 endpoint/schema 미정

**왜 바뀌었나**: 개발팀 구현은 지표별 endpoint를 분리하고 실제 DB가 바로 제공할 수 있는 응답을
기준으로 진행 중이다. 제품 문서가 독자적인 bundle JSON을 정본처럼 갖고 있으면 API와 화면이 동시에
두 개의 계약을 갖게 된다. 따라서 기획은 “무엇을 보여줘야 하는가”를 정의하고 wire shape는 API 정본에
맡기는 쪽으로 책임을 분리했다.

| 문서 | 위치 | 0909 | 0910 |
|---|---|---|---|
| 서비스 기획서 | §6.5, §7.2~7.4 | API endpoint/wire 경계가 제품 문서에 명확하지 않음 | Notion/Swagger 정본, version query, adapter delta, weekly 78주 명시 |
| 요구사항 명세서 | 변경이력, 공통-R03, 기능-06/07 | 제품 상태 중심 | API data_status 6종, version query, adapter delta, 78주 완료 조건 |
| 메뉴구조 IA | 화면01, Dependency/Activity state | API 동작과 화면 구조 연결이 약함 | autocomplete gate, version filter, weekly/78주, state 위치 명시 |
| 기능별 개발 구상안 | §1.5, §4.0, §4.3, §5.2~5.4 | 기획 JSON과 시스템 계약 혼재 | Notion/Swagger 정본, wire boundary, 후보 API 미정 |
| API 정합 요약 | 신규 | 없음 | 기획 확정 / Notion 반영 대기 / OPEN을 분리 |

**중요한 구현 상태**: 0910에 전달받은 Notion endpoint export의 검색·개요·Downloads·Dependents·
Version Share 5개 항목은 모두 `서버 반영=No`였다. 따라서 `version`, `relationship_type`, 공통
`data_status`, 78주 validation 등은 **기획 결정이 확정됐다는 뜻이지 구현 완료됐다는 뜻이 아니다.**

## 결정 3 — 패키지 입력을 수동 존재 확인에서 autocomplete selection gate로 변경

**무엇이 바뀌었나**: 0909 화면-01은 패키지명을 입력하고 `패키지 확인` 버튼으로 존재 여부를 검증한
뒤 다음 단계로 이동하는 구조였다. 0910은 사용자가 접두사를 입력하면 DB의 분석 가능한 패키지 목록을
보여주고, **실제 결과 항목을 직접 선택해야** 기준 패키지가 확정되고 다음 CTA가 활성화되는 구조로
바뀌었다.

자동완성은 접두사 일치 목록일 뿐, 오타를 추측해 다른 이름으로 바꾸거나 유사 패키지를 추천·확정하는
기능이 아니다. 화면-02의 직접 추가도 같은 selection gate를 재사용한다.

**왜 바뀌었나**: 현재 시스템은 다음 단계에 필요한 DB 정보가 있는 패키지만 검색 단계에서 선택할 수
있도록 설계되어 있다. 따라서 사용자가 임의 문자열을 들고 다음 화면에 들어간 뒤 `package_not_found`
또는 정보 부족 오류를 처리하는 UX를 별도로 만드는 것은 실제 흐름과 맞지 않는다.

| 문서 | 위치 | 0909 | 0910 |
|---|---|---|---|
| 서비스 기획서 | §6.2, MVP 완료범위, 문제-기능 연결 | 패키지 입력/존재 확인 | 접두사 자동완성 + 분석 가능한 항목 선택 gate |
| 요구사항 명세서 | 화면-01, 기능-01·02, 공통-R14 | `패키지 확인` 버튼, 확인 중/성공/실패 | 검색 결과 직접 선택 전 CTA 비활성 |
| 메뉴구조 IA | §5 화면-01 | 입력 우측 `패키지 확인` | autocomplete list + selected package + CTA |
| 기능별 개발 구상안 | §4.0 | npm 존재 확인 중심 | `/packages/search?q=` selection gate, 직접 추가도 재사용 |
| Figma | `485:275`, 화면00/Requirement Map | 입력 + `패키지 확인` + “npm에서 확인됨” | `pin` → 목록 → `pino` 선택 → 다음 CTA |

## 결정 4 — EXT-01/02/04를 “새 화면”이 아니라 생태계 보고서 내부 확장으로 재정의 (`DEC-ECOSYSTEM-INPAGE-EXT-20260910-01`)

**무엇이 바뀌었나**: 0909 IA/Figma에서는 간접·전이 Dependency 등 일부 확장 기능이 별도 분석
화면처럼 읽혔다. 0910은 확장 기능의 UI 소유권을 다음과 같이 고정했다.

- EXT-01 버전 고착: 화면03A Version Share 아래 인페이지 모듈
- EXT-02 관측된 교체 흐름: EXT-01 아래 인페이지 모듈
- EXT-04 간접·전이 Dependency: 기존 Dependency 카드 안의 `직접 | 간접·전이` 범위 전환
- 기능 비교와 GitHub 커뮤니티만 실제 확장 report tab

EXT-01에는 `pino / winston / bunyan`처럼 분석 패키지를 고르는 탭을 두고 한 번에 한 패키지의
고착 분포를 본다. EXT-02는 3개 패키지에서 가능한 최대 6개의 directed edge를 표가 아니라
`FROM → TO` flow map으로 보여주며, `전체 / package focus`를 지원한다.

**왜 바뀌었나**: EXT-01/02는 생태계 변화 보고서의 추가 해석이고 EXT-04는 Dependency 그래프의
scope 변경이다. 이들을 route/tab으로 만들면 제품 IA가 실제 의미보다 커지고 사용자가 새로운 보고서로
이동한다고 오해한다. 특히 3개 패키지의 A↔B↔C 6방향 교체 관측을 표로만 나열하면 방향성이 읽히지
않아 flow map을 기본 표현으로 정했다.

| 문서 | 위치 | 0909 | 0910 |
|---|---|---|---|
| 서비스 기획서 | §7.7 | 확장 목록 중심, 상세 UI 소유권 없음 | 03A 내부 EXT-01/02/04 위치와 동작 명시 |
| 요구사항 명세서 | §12.2~12.4 | 확장 기능 내용 중심 | package tabs, 최대 6 directed edges/focus, Dependency scope switch |
| 메뉴구조 IA | §4/§8.6/Figma 연결 | EXT-04 별도 분석 화면처럼 표현 | 03A 하위 state/reference로 변경 |
| 기능별 개발 구상안 | §12.1~12.2/§12.5 | 분석 로직 중심 | UI ownership + directed edge/focus 계약 추가 |
| Figma | `485:1058`, `489:292` | Future Modules / 별도 확장 페이지 인상 | in-page modules / Dependency scope states |

## 결정 5 — 실제 서버 사양·컴포넌트 배치로 인프라 정합 (`DEC-SERVER-ALIGN-20260910-01`)

**무엇이 바뀌었나**: 0909 개발 구상안은 두 대의 `t4g.xlarge`, #1 MinIO `EBS 200GB`,
`#2:443` 단일 외부 인바운드 등을 시스템 확정안으로 적고 있었고 Redis와 Spark History Server를
향후 운영 확장으로 분류했다. 0910은 개발팀의 실제 `서버 정보.pdf`를 물리 인프라 정본으로 올렸다.

최종 물리 기준:

| 서버 | 실제 사양 | 현재 배치 |
|---|---|---|
| #2 app | 4 vCPU · Xeon Platinum 8175M 2.50GHz · 15Gi RAM · Swap 0 · 320G NVMe | nginx, 프론트 정적, 백엔드 API, PostgreSQL+pgvector, Redis, Spark worker-2 |
| #1 data | 4 vCPU · Xeon Platinum 8259CL 2.50GHz · 15Gi RAM · Swap 0 · 320G NVMe | Spark master, worker-1, History Server, 임베딩 추론/tarball 정적분석/PDF worker, MinIO |

서비스 외부 노출은 #2 app의 80/443이고 #1 data는 사용자 서비스 포트를 외부에 노출하지 않는 것으로
정리했다. PDF 생성 실행 위치는 #1 data worker로 맞췄다.

**왜 바뀌었나**: 0909의 인스턴스 타입과 스토리지 용량은 실제 배정 서버와 맞지 않았다. 특히 두
서버가 모두 4 vCPU/15Gi/320G라는 실측 한계 안에서 여러 컴포넌트를 함께 실행하므로, 가상의
`t4g.xlarge` 자원 전제를 그대로 두면 Spark/분석 worker 동시성과 저장 용량 판단이 잘못된다.

| 문서 | 위치 | 0909 | 0910 |
|---|---|---|---|
| 기능별 개발 구상안 | §3.1~3.9 | `t4g.xlarge` 2대, #2 서빙/#1 배치 가정 | 실제 #2 app/#1 data 사양·컴포넌트 배치 |
| 기능별 개발 구상안 | 저장/운영 | MinIO `EBS 200GB`, Redis/History 향후 확장 | #1 320G host disk, Redis/History 현재 배치 |
| 기능별 개발 구상안 | PDF | 생성 위치/전달 관계가 모호 | #1 PDF worker 실행, #2→#1 전달은 OPEN |
| 서비스/요구사항/IA | 인프라 세부 | 직접적인 물리 사양 거의 없음 | 상세 사양을 개발 구상안에 위임, 제품 계약 중복 생성 안 함 |
| Figma Requirement Map | system contract 요약 | 이전 아키텍처 요약 | #1/#2 실제 배치와 사양 요약 |

**의도적으로 정하지 않은 것**: Redis의 실제 key/TTL/책임, MinIO 예약 용량, PDF queue/dispatch,
CI runner/registry/deploy command, 외부 GPU/MLflow 물리 사양은 서버 자료가 보장하지 않으므로
OPEN으로 남겼다.

## 결정 6 — 최종 재검수에서 데이터 해석·상태·PDF 세부 계약 보강

**무엇이 바뀌었나**: 핵심 0910 결정을 반영한 뒤 API 자료·서버 자료·Figma를 다시 교차검사하면서
기능을 새로 추가한 것이 아니라 **오해 가능성이 있는 경계 조건**을 보강했다.

- Dependency Total은 고유 프로젝트 수가 아니라 버전별 `dependents_count` 합계라고 명시
- 다중 패키지 Dependency/Downloads 추이는 로그축 사용
- 유효 trend point가 2개 이하이면 `데이터 축적 중 (N주차)` 표시
- visible range 안의 첫·마지막 유효 point를 delta 기준으로 통일
- PDF 생성 실패 `FAILED`와 생성 완료 후 다운로드 실패를 분리
- PDF의 GitHub 커뮤니티 확장 부록도 기준 패키지 하나만 대상으로 정합
- 서버 정합 중 빠질 수 있던 Spring→GMS bounded 예외 복원
- Figma old Snapshot pair를 조회 구간 첫·마지막 기준으로 정리하고 standalone “18개월”, hidden retained/inflow/outflow reference 정리

**왜 바뀌었나**: 개별 문서만 읽으면 문제가 없어 보여도 API의 데이터 의미, 화면의 예시 문구,
PDF의 재현 방식까지 이어서 보면 잘못 구현될 수 있는 구간이 남아 있었다. 이 단계에서는 새로운
알고리즘을 만들지 않고 기존 정본이 이미 말하는 의미를 문서에 전달하는 데만 집중했다.

## 유지된 것

- `DEC-RANK-20260909-01`: deprecated 후보 완전 제외, top-K 20, Recall@20, cos 기반 재랭킹,
  `move_lift` 미사용.
- `DEC-COMMUNITY-20260909-01`: GitHub 커뮤니티는 기준 패키지 하나만 분석하며 다른 비교
  패키지로 fallback하지 않는다.
- 같은 결정의 Spring→GMS 직접 호출은 확장-03 refresh에 한정된 bounded 예외로 유지한다.
- 기준 패키지는 항상 비교 대상에 포함되고 해제할 수 없다.
- 한 보고서의 최종 비교 대상은 기준 패키지 포함 최대 3개다.
- 후보 상위 2개 기본 선택은 최종 추천이나 기술 품질 순위가 아니다.
- 후보 단계에서는 버전을 선택하지 않는다.
- Version Share UI는 최신 Snapshot이고 시계열이 아니다.
- 기능 비교와 GitHub 커뮤니티는 MVP가 아닌 확장이다.
- Pickage는 “가장 좋은 패키지”를 자동 선택하거나 승자를 선언하지 않는다.

## 문서별 변경 규모 참고

아래 line diff는 변경량을 이해하기 위한 참고치이며 기능 수를 의미하지 않는다.

| 문서 | 0909 lines | 0910 lines | 추가 line | 삭제 line |
|---|---:|---:|---:|---:|
| 서비스 기획서 | 658 | 710 | 78 | 26 |
| 요구사항 명세서 | 500 | 559 | 114 | 55 |
| 메뉴구조 IA | 580 | 634 | 94 | 40 |
| 기능별 개발 구상안 | 1,156 | 1,316 | 370 | 210 |

## 변경 대상에서 제외하거나 보존한 것

- 0909 네 원본 문서는 비교 baseline으로 보존하고 덮어쓰지 않았다.
- 0909 ranking 구조의 top-K 20/Recall@20/deprecated drop은 이번 API·서버 정합을 이유로 다시
  바꾸지 않았다.
- GitHub 커뮤니티의 기준 패키지 단일화와 Spring-GMS 한정 예외도 서버 정합 과정에서 폐기하지 않았다.
- 기능 비교 POC 결과는 확장 기술 가능성 참고 자료로 유지하되 MVP 완료 조건으로 승격하지 않았다.
- Figma V1 archive는 변경 대상이 아니며 V2만 제품 정본 화면으로 검수했다.

## 후속 필요 항목 (현재 의도적으로 OPEN)

- 후보 ranking API endpoint/schema/관련성 근거 전달 field — 임베딩 모델 실결과 확인 후 확정.
- Version Share API의 historical `snapshot_at` 지원 여부.
- Version Share `해석 불가` bucket의 실제 HTTP wire 표현.
- `OPEN-SERVER-01`: #2 app → #1 data PDF worker의 job 전달/queue/polling과 UI-derived delta를
  동일 PDF Snapshot으로 넘기는 방식.
- `OPEN-SERVER-02`: Redis 실제 key/TTL 및 세션·캐시·job 책임.
- `OPEN-SERVER-03`: 실제 CI runner/container registry/deploy command.
- MinIO 예약 용량·보존/정리 정책.
- 외부 GPU/MLflow 물리 사양.

이 OPEN 항목은 문서 누락이 아니라 현재 자료가 결정을 지원하지 않는 영역이다. 정본이 나오기 전에
구체 구현을 채워 넣으면 오히려 0910 최종 세트의 정합성을 깨뜨린다.
