# 제출 산출물 생성기 — ERD · 시스템 아키텍처 · API 명세서

대회 제출용 PDF 3종을 만든 생성기다. 완성본 PDF 는 `docs/` 루트에 있고, 이 폴더는 그것을
만든 과정(입력 스냅샷·생성 코드)을 보관한다. **PDF 는 손으로 고치지 않는다** — 코드에서 다시 뽑는다.

| 파일 | 내용 | 원본 |
| --- | --- | --- |
| [`docs/Pickage_ERD.pdf`](../../Pickage_ERD.pdf) | A3 ERD 그림 + 개요·관계 요약 + 테이블 정의서 16개 | Flyway V1~V13 을 빈 DB 에 적용한 스키마 |
| [`docs/Pickage_시스템_아키텍처.pdf`](../../Pickage_시스템_아키텍처.pdf) | ① 배포 구성도 ② 기능별 처리 흐름 (A3 가로 2쪽) | `deploy/prod/*/compose.yaml`, 코드 구조 — 손으로 그린 SVG |
| [`docs/Pickage_API_명세서.pdf`](../../Pickage_API_명세서.pdf) | 공통 규칙·오류 코드·목록 + 엔드포인트 27개 상세 | springdoc OpenAPI, 컨트롤러·DTO 소스, FastAPI `openapi()` |

## 다시 만들기

```bash
# 코드만 바뀌었으면(DTO 설명·컨트롤러 설명) 이것 하나면 된다
python docs/history/제출산출물/src/build.py

# 마이그레이션·엔드포인트가 바뀌었으면 입력부터 다시 뽑는다
sh docs/history/제출산출물/src/refresh_inputs.sh
python docs/history/제출산출물/src/build.py
```

- PDF 변환은 Chrome headless 를 쓴다. 기본 설치 경로가 아니면 `CHROME` 환경변수로 실행 파일을 지정한다.
- `refresh_inputs.sh` 는 **일회용 Postgres 컨테이너**(`pickage-docgen-pg`, 15499)를 띄워 쓰고 지운다.
  실데이터가 든 로컬 DB(`pickage-local-postgres`, 15432)는 건드리지 않는다.
- PDF 는 `docs/` 루트에 덮어쓴다. 중간 HTML 은 이 폴더의 `build/` 에 생긴다(추적하지 않음). 브라우저로 열어 미리 볼 수 있다.

## 구성

| 경로 | 역할 |
| --- | --- |
| `src/build.py` | HTML 생성 + PDF 변환 |
| `src/javasrc.py` | 백엔드 DTO record·컨트롤러 파서. springdoc 이 `ApiResponseBody<T>` 의 T 를 지워 응답 필드가 비어 나오므로 소스에서 직접 읽는다 |
| `src/notes.py` | 원본에 설명이 없는 자리만 사람이 채운 것 — 테이블·컬럼 설명, 파라미터 설명, 엔드포인트별 오류, ERD 배치 |
| `src/architecture.html` | 시스템 아키텍처 (SVG·HTML 을 직접 편집) |
| `src/style.css` | 공통 인쇄 스타일 (A4 세로, 그림 쪽만 A3 가로) |
| `src/data/*.json` | 생성기 입력 스냅샷 — 스키마, 백엔드 OpenAPI, RAG OpenAPI |

## 설명을 고치고 싶을 때

설명의 정본은 코드다. 우선순위는 다음과 같다.

1. DB 컬럼 — `COMMENT ON` (마이그레이션) → 없으면 `notes.COLUMNS`
2. API 응답·요청 필드 — DTO 의 Javadoc `@param` → 없으면 `notes.FIELDS`
3. 엔드포인트 요약·설명 — 컨트롤러 `@Operation`

새 테이블이 생기면 `notes.TABLES`·`notes.LAYOUT` 에, 새 엔드포인트가 생기면 `notes.PATH_ORDER` 에
추가하지 않으면 생성기가 멈추고 무엇이 빠졌는지 알려 준다. 시스템 아키텍처는 자동 생성이 아니므로
서비스 구성이 바뀌면 `src/architecture.html` 을 함께 고친다.
