# Pickage 기능별 개발 구상안 — 2026-09-23 완성 기준

> 구현 기준: `origin/develop` `c88e20a`
> 성격: 미래 아키텍처 제안이 아니라 현재 구현된 구조와 운영 경계를 설명하는 설계 정본

## 1. 시스템 개요

Pickage는 브라우저, Spring Boot API, Python RAG·유사도 작업, PostgreSQL, MinIO·MLflow,
배치 파이프라인으로 구성된다.

```text
Browser (React/Vite)
  └─ /api
     └─ Spring Boot API
        ├─ PostgreSQL / Flyway V1~V13
        ├─ RAG API (FastAPI, README HAND-OFF 근거)
        ├─ PDF / Markdown generator
        └─ Community collector / GMS summarizer

Data node
  ├─ MinIO: raw, bronze, curated, models, MLflow artifacts
  ├─ MLflow: similarity model registry
  ├─ Spark master + worker 1
  ├─ registry/deps.dev/downloads collectors
  └─ weekly ingest timer

App node
  ├─ nginx web + TLS
  ├─ API / RAG API / PostgreSQL
  ├─ Spark worker 2
  └─ similarity / package_env loaders
```

로컬은 단일 Spark 컨테이너와 named volume MinIO를 사용하며 운영과 동일한 분산 환경이 아니다.

## 2. 프런트엔드

### 2.1 기술 구성

- React 19, TypeScript 6, React Router 7
- TanStack Query 5로 서버 상태 관리
- Tailwind CSS 4
- Vite 8, Vitest 5

라우트는 소개, 분석 구성, 보고서의 세 단계다. 비교 패키지 목록은 URL 쿼리를 공유 가능한 최소
상태로 삼고, 탭별 데이터와 실행 상태는 query cache·화면 상태로 관리한다.

### 2.2 후보 선택

입력은 기준 패키지 이름이다. 백엔드 유사도 API가 제공한 후보를 최대 3개 보여 주며 UI가 임의로
상위 2개를 선택하지 않는다. 직접 추가는 사용 가능 패키지 검색과 overview 검증을 거친다. 총 비교
이름은 3개로 제한한다.

URL 동기화는 `base`, `with`, `nosimilar`, `names` 계약을 사용한다. 현재 직접 추가의 빠른 연속 조작
경합은 후속 버그 범위다.

### 2.3 보고서 탭

세 탭은 lazy import한다. 방문한 탭은 mount를 유지해 기능 비교 결과와 차트 상태를 보존하고, 활성 탭
여부가 필요한 polling에는 별도 flag를 전달한다. 각 feature는 query·표현·오류 경계를 가진다.

## 3. Spring Boot API

### 3.1 공통 계약

- Java 21, Spring Boot 4
- API 응답 snake_case
- 비교 이름 최대 3개
- Flyway가 스키마를 소유하고 JPA는 `validate`
- 외부 요청과 장시간 작업의 실패를 도메인 오류로 변환

### 3.2 엔드포인트

| 영역 | 메서드·경로 | 역할 |
| --- | --- | --- |
| 패키지 | `GET /api/packages` | 패키지 개요 |
| 생태계 | `GET /api/packages/downloads` | 다운로드 주간 추이 |
| 생태계 | `GET /api/packages/dependents` | 의존 패키지 주간 추이 |
| 생태계 | `GET /api/packages/version` | 버전 점유율 |
| 후보 | `GET /api/packages/similar` | 유사 후보 |
| 생태계 | `GET /api/packages/transitions` | 의존 전환 |
| 생태계 | `GET /api/packages/removal-reasons` | 제거 이유 |
| 생태계 | `GET /api/packages/migration-pairs` | 관측 이동 경로 |
| 검색 | `GET /api/packages/search` | 제공 가능 패키지 검색 |
| 요약 | `GET /api/packages/summary` | 실험적 생태계 요약 |
| 커뮤니티 | `GET /api/packages/community` | snapshot 조회 |
| 커뮤니티 | `POST /api/packages/community/refresh` | 비동기 갱신 |
| 기능 | `GET /api/packages/versions` | 버전 후보 |
| 기능 | `GET /api/packages/env` | 실행 환경 |
| 기능 | `POST /api/packages/feature-comparison` | 비교 실행 |
| 기능 | `GET /api/packages/feature-comparison/{runId}` | 비교 상태·결과 |
| PDF | `POST /api/report/pdf` | 생성 |
| PDF | `GET /api/report/pdf/{id}` | 상태·메타데이터 |
| PDF | `GET /api/report/pdf/{id}/preview` | HTML 미리보기 |
| PDF | `GET /api/report/pdf/{id}/file` | 파일 |
| Markdown | `POST /api/report/markdown` | 생성 |
| Markdown | `GET /api/report/markdown/{id}` | 상태·메타데이터 |
| Markdown | `GET /api/report/markdown/{id}/file` | 파일 |

`/api/v1/ops/weekly/**`는 실행 조회·수동 요청용 내부 API다. nginx에서 차단하고 OpenAPI에서 숨긴다.

### 3.3 실행 상태 저장

기능 비교와 출력 작업은 현재 JVM 프로세스 메모리에 상태를 둔다. 구현이 단순하고 세션 응답이 빠른
대신 서버 재시작·다중 인스턴스에서 복구되지 않는다. 사용자 계정·보고서 보관함이 없는 현재 제품
범위에서는 허용한 제약이며, 영속 job store를 이미 구현한 것으로 표현하지 않는다.

## 4. 생태계 데이터

### 4.1 핵심 저장 구조

| 마이그레이션 | 핵심 내용 |
| --- | --- |
| V1 | package, package_snapshot, version, snapshot, package_version_snapshot |
| V2~V3 | ETL 실행·시도·현재 데이터셋·snapshot reference |
| V4 | similar_package |
| V5 | community_snapshot |
| V6~V7 | package_version_snapshot 파티션·제약 정리 |
| V8 | dependent_transition |
| V9 | dependent_removal_reason |
| V10 | package_env |
| V11 | 미관측 freshness 열 |
| V12 | available_package |
| V13 | migration_pair |

### 4.2 다운로드·Dependents·버전

다운로드는 npm 범위 수집을 주간 값으로 제공한다. Dependents는 deps.dev의 버전별 소비 관계를
집계하므로 절대값 중복 가능성을 API와 UI에서 고지한다. Version share는 패키지 내부 분포로만
해석한다.

### 4.3 전환

전환 데이터는 기간과 dependency kind별로 유지·유입·유출·미관측을 계산한다. V11의 freshness
정보로 데이터 미도달을 실제 유지와 구분한다. 제거 이유는 관측된 전환 이벤트를 분류한다.

### 4.4 관측 이동 경로

regular·dev 데이터셋을 별도 생성한다. API의 공통 필터는 `votes >= 5`,
`publisher_months >= 3`이며 `share_pm_pct` 순으로 상위 5개와 나머지를 접는다. 양방향 여부와 등급은
근거 숫자를 함께 제공한다.

통계 필터는 한 조직의 일괄 변경을 상당 부분 거르지만 `rxjs → tslib` 같은 딸려 들어온 부품이나 같은
시기의 무관한 변경을 완전히 분리하지 못한다. 따라서 설계상 이름도 “관측 이동”으로 유지한다.

## 5. 유사 패키지 AI

### 5.1 모델과 배치

- 모델 레지스트리: MLflow `pickage-similarity@production`
- 현재 기록 모델: version 2, `v7-v5clean`
- 임베더: `BAAI/bge-small-en-v1.5`, 384차원, ONNX
- 입력: description + keywords
- 벡터: CLS pooling 후 L2 정규화

배치는 의미 유사 상위 30을 얻은 뒤 플러그인·어댑터, 같은 family, archived, 보완 관계, dependents
관문을 적용한다. 다운로드 인기도 하한은 후보가 부족할 때 `500k → 100k → 50k → 10k → 0`으로
완화하고 최종 코사인 순으로 저장한다.

서버에는 더 많은 후보를 저장할 수 있지만 프런트는 최대 3개를 노출한다. 현재 배치 `max-rank` 기본은
100k이며 468k 전체 배치는 완료 범위가 아니다.

### 5.2 모델 품질·자원 경계

최신 기록은 29,376 코퍼스·315 평가쌍에서 recall@3 0.238, recall@10 0.511,
recall@30 0.740이다. 첫 운영 배치 최고 메모리는 약 5.236 GiB로 8 GiB 설정에서 성공했다.
이 수치는 사용자에게 정확도 보증으로 제시하기보다 모델 선택과 운영 용량의 근거로 사용한다.

## 6. 기능 비교 RAG

### 6.1 입력과 검색

RAG API는 패키지명·버전 목록을 받는다. 각 패키지 버전의 HAND-OFF Markdown에서 메타데이터 헤더와
README 청크를 읽고 패키지당 12,000자 예산 안에서 관련 근거를 구성한다. DB 벡터 저장소나 pgvector는
현재 구조에 없다.

### 6.2 생성 계약

한 번의 구조화 생성 호출로 다음을 반환한다.

- `dataStatus`: `COMPLETE` 또는 `COMPARISON_LIMITED`
- 공통점 설명
- 패키지별 차이 설명
- `KEY_TERM`, `KEY_SENTENCE` 강조 구간
- 패키지별 source 상태

생성 결과는 순위나 추천을 만들지 않는다. 근거에 없는 널리 알려진 설명이 꼭 필요하면 “일반적으로”로
구분한다. 문서가 없으면 `DOC_NOT_FOUND`, 출력 계약을 검증하지 못하면 실패로 반환한다.

### 6.3 저장과 재시도

RAG 결과는 영구 저장하지 않고 자동 재시도하지 않는다. Spring API의 run 상태도 메모리다. 같은
입력으로 다시 요청할 수 있지만 기존 run의 영구 복원을 보장하지 않는다.

## 7. GitHub 커뮤니티

### 7.1 수집 경계

기준 패키지의 repository를 확인한 뒤 GitHub의 활동·이슈·PR·기여 관련 지표를 모은다. 조회 GET과
외부 수집 POST를 분리해 단순 화면 새로고침이 API 호출량을 늘리지 않게 한다.

### 7.2 요약

GMS Responses 호환 API를 사용해 구조화 요약을 생성한다. 원천 수치와 생성 요약의 책임을 분리하고,
부분 자료·실패 상태를 snapshot에 보존한다. 커뮤니티를 단일 건강도 점수로 환원하지 않는다.

### 7.3 갱신

분석 확정 시 refresh를 비동기로 요청한다. 기존 snapshot이 있으면 사용자에게 먼저 제공하고 상태를
polling한다. 이 흐름은 보고서 진입을 차단하지 않는다.

## 8. PDF와 HAND-OFF

PDF 생성기는 생태계 섹션을 항상 포함하고 요청한 커뮤니티와 현재 기능 비교 결과를 합성한다. HTML
preview와 PDF 파일은 같은 데이터 소스를 사용한다. 자료가 없으면 섹션을 조용히 삭제하지 않고 제한을
기록한다.

Markdown 생성기는 사람이 읽는 장식보다 에이전트가 다시 사용할 구조, 기준일, 단위, 결측을 우선한다.
현재 세션의 기능 비교 결과는 요청 payload로 전달하며 서버에서 별도 조회 가능한 영구 결과는 아니다.

## 9. 파이프라인

### 9.1 레이어

1. npm registry, deps.dev BigQuery, npm downloads, GitHub 원천 수집
2. raw·Bronze를 MinIO/GCS에 회차별 저장
3. DuckDB·Spark로 Curated·파생 지표 생성
4. loader가 PostgreSQL stage·검증·게시
5. API가 현재 dataset pointer와 스키마를 통해 제공

### 9.2 현재 규모 경계

확장 target은 468,519개다. package snapshot 전수와 확장 transition·downloads 기반이 있으나
similarity 기본 상한은 100k이고 최신 dependents 재계산은 미병합이다. package_env는 추가 registry
회차를 합치는 코드와 로컬 검증이 있으나 운영 확장 게시 여부는 별도 확인한다.

### 9.3 주간 자동화

데이터 노드 timer가 화요일 10:00 KST 회차를 대상으로 deps.dev T2, GCS 동기화, downloads,
parquet, Bronze 적재를 실행한다. 10분 주기는 회차 조건을 확인하는 빈도이며 매번 전체 수집한다는
뜻이 아니다. 후속 Curated·PostgreSQL 게시 전체를 주간 runner의 책임으로 섞지 않는다.

## 10. 배포·네트워크

### 10.1 로컬

`compose.yaml`은 PostgreSQL, API, MinIO, minio-init, Spark, similarity를 제공한다. 프런트는
`npm run dev`로 별도 실행한다. Spark는 local mode이고 MinIO는 서비스 이름 endpoint와 named
volume을 사용한다.

### 10.2 운영

앱 노드는 nginx TLS, API, RAG, PostgreSQL과 loader를, 데이터 노드는 MinIO, MLflow, Spark
master, 배치 서비스를 담당한다. Spark worker는 두 노드에 있고 host network와 사설 endpoint를
사용한다. 운영 MinIO 데이터 디렉터리는 `/srv/minio/data`이며 로컬보다 오래된 콘솔 호환 버전을
의도적으로 고정한다.

### 10.3 자원·보안

운영 컨테이너는 `mem_limit`과 같은 `memswap_limit`을 사용하므로 상한 초과 시 즉시 OOM Kill될 수
있다. nginx는 SPA fallback을 제공하고 ops API를 차단한다. 시크릿은 환경 변수와 배포 환경에만 둔다.

## 11. 검증 전략

- 프런트: typecheck, ESLint, Vitest, production build
- 백엔드: 단위·통합 테스트, Testcontainers, compile 검증
- AI/RAG: pytest, schema·강조 구간 검증
- 파이프라인: 모듈별 unit·smoke와 데이터 회차 검증
- 배포: compose config, healthcheck, nginx route, loader verify-only

현재 `python -m pytest pipeline` 전체 실행은 collection 구조와 PySpark 환경 문제로 실패한다. 테스트
파일이 존재한다는 사실과 한 명령·CI로 전부 검증된다는 주장을 구분한다.

## 12. 알려진 기술 부채

- 메모리 job store의 재시작·다중 인스턴스 비호환
- 468k 전체 similarity와 최신 dependents 범위 불일치
- pipeline 전체 테스트 실행 계약 부재
- 앱·데이터 노드 모니터링 배포 상태 차이
- README와 CI 주석의 과거 상태 표현
- 이동 경로에서 대체가 아닌 동시 변경을 가르는 의미 축 부족

## 13. 관련 문서

- [서비스 기획서](Pickage_서비스_기획서_0923.md)
- [요구사항 명세서](Pickage_요구사항_명세서_0923.md)
- [메뉴구조·IA](Pickage_메뉴구조_IA_0923.md)
- [개발 현황 조사 보고서](worklogs/S15P21A506-473/01_개발현황_조사보고서_260923.md)
