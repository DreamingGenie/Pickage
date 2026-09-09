# Pickage 0902 → 0904 기획 변경 상세 분석

> 비교 대상: 2026-09-02 `OSS Shift` 기획 문서 4종 ↔ 2026-09-04 `Pickage` 기획 문서 4종  
> 작성 목적: 단순 문장 수정 이력이 아니라, **0902에서 0904로 제품 정의·MVP 범위·화면 계약·요구사항·기술 아키텍처가 어떻게 바뀌었는지 추적 가능한 변경 기록**을 남긴다.  
> 분석 기준: 사용자가 제공한 8개 Markdown 원문만을 기준으로 하며, 문서에 없는 의도는 사실처럼 보충하지 않는다.

---

## 0. 문서 목적과 비교 기준

0904는 0902 문서의 단순 교정본이 아니다. 4개 문서를 함께 비교하면 다음과 같은 변화가 동시에 발생했다.

1. 서비스명이 `OSS Shift`에서 `Pickage`로 확정되었다.
2. MVP의 중심이 **생태계 변화 + 정확한 버전 기능 비교**에서 **현실적인 비교 후보 발견 + 직접 의존 생태계 분석**으로 좁혀졌다.
3. 기능 비교와 Evidence Drawer는 삭제되지 않고 **확장 기능으로 이동**했다.
4. 후보 추천은 설명 유사도 중심에서 **의미 후보 탐색 + 생태계 이동 신호 기반 재랭킹** 구조로 구체화되었다.
5. Dependency는 MVP에서 **직접 의존만** 다루도록 범위를 제한했다.
6. Version Share는 시계열 해석 가능성을 제거하고 **최신 기준일 Snapshot**으로 의미를 고정했다.
7. MVP PDF는 기능 비교 완료 여부와 분리되어 **생태계 결과만으로 생성 가능**하게 바뀌었다.
8. GitHub Community는 단순 요약에서 **요약·수치 → 핵심 이슈·쟁점 → 실제 논의 흐름**의 3단 구조로 고도화되었다.
9. 반응형·모바일 계약을 제거하고 **데스크톱 웹 전용**으로 제품 제공 범위를 고정했다.
10. 개발 구상안이 ‘권장 구조’에서 **v1 시스템 아키텍처 확정안**으로 격상되었다.

이 문서는 위와 같은 **의미 단위 변경**을 중심으로 분석한다.

### 0.1 비교 문서

| 역할 | 0902 | 0904 |
|---|---|---|
| 서비스 정책·범위 | `OSS_Shift_서비스_기획서_0902(1).md` | `Pickage_서비스_기획서_0904.md` |
| 메뉴·화면·상태 배치 | `OSS_Shift_메뉴구조_IA_0902(2).md` | `Pickage_메뉴구조_IA_0904.md` |
| 사용자 요구·완료 기준 | `OSS_Shift_요구사항_명세서_0902(1).md` | `Pickage_요구사항_명세서_0904.md` |
| 데이터·처리·기술 | `OSS_Shift_기능별_개발_구상안_0902(1).md` | `Pickage_기능별_개발_구상안_0904.md` |

### 0.2 문서별 역할

- **서비스 기획서**: 왜 이 서비스를 만들고 무엇을 MVP/확장으로 제공하는지 정의한다.
- **IA**: 그 기능이 어느 화면에 있고 사용자가 어떤 순서로 조작하는지 정의한다.
- **요구사항 명세서**: 기능·상태·예외의 완료 조건을 정의한다.
- **개발 구상안**: 요구 결과를 만들기 위한 데이터·배치·캐시·모델·서버·배포 계약을 정의한다.

따라서 동일한 변경이 네 문서에 반복되어 보이더라도 각각의 역할이 다르다. 본 분석에서는 **하나의 제품 결정이 네 문서에 어떻게 전파되었는가**를 중심으로 본다.

### 0.3 변경 유형

| 태그 | 의미 |
|---|---|
| `신규` | 0902에는 없던 기능·정책·기술 계약이 0904에 새로 생김 |
| `변경` | 기존 정책이나 동작의 의미가 달라짐 |
| `범위 이동` | 기능은 유지되나 MVP/확장 등 출시 범위가 달라짐 |
| `구체화` | 방향만 있던 항목이 계산식·상태·화면·기술 계약으로 구체화됨 |
| `삭제/제외` | 0902에 있던 제공 범위가 0904에서 제거됨 |
| `명칭/표현` | 서비스명·용어·설명 방식 위주의 변경 |

### 0.4 중요도

| 등급 | 기준 |
|---|---|
| `P0` | 제품 정의, MVP 완료 조건, 핵심 사용자 여정 자체가 달라짐 |
| `P1` | 핵심 기능의 동작·해석·화면 계약이 달라짐 |
| `P2` | 데이터·기술·운영 구현의 기준이 달라짐 |
| `P3` | 명칭·표현·세부 위치·문구 수준 변경 |

---

## 1. Executive Summary

### 1.1 한 문장 요약

**0902가 ‘후보 발견부터 정확한 버전 기능 근거까지 한 번에 완성하는 넓은 MVP’였다면, 0904는 ‘현실적인 후보를 찾고 직접 의존 생태계 변화를 설명하는 MVP’를 먼저 완결하고, 기능 비교·RAG·GitHub 논의 분석을 확장으로 분리한 버전이다. 동시에 개발 구조는 추상적 권장안에서 실제 배포 가능한 EC2 2대 중심 확정 아키텍처로 구체화되었다.**

### 1.2 문서 규모 변화

아래 수치는 단순 텍스트 변화량이며, 기획 변경의 중요도와 동일하지 않다.

| 문서 | 0902 라인 | 0904 라인 | 증감 | 특징 |
|---|---:|---:|---:|---|
| 서비스 기획서 | 567 | 653 | +86 | MVP 재정의, 후보 랭킹·GitHub 3단 구조 추가 |
| 메뉴구조 IA | 478 | 555 | +77 | 확장 구분, 데스크톱 전용, GitHub 화면 상세화 |
| 요구사항 명세서 | 455 | 499 | +44 | Scope 재분류, 후보 랭킹·간접 Dependency·PDF 조건 변경 |
| 개발 구상안 | 899 | 1,139 | +240 | 확정 시스템 아키텍처·모델 사이클·저장/운영 계약 대폭 추가 |

개발 구상안의 증가폭이 가장 크다. 이는 0904에서 기술 문서의 성격이 **‘권장 구현안’ → ‘v1 구현 기준’**으로 변한 것과 직접 관련된다.

### 1.3 가장 중요한 변화 요약

| Change ID | 변경 | 유형 | 중요도 |
|---|---|---|---|
| CHG-01 | OSS Shift → Pickage 브랜드 확정 | 명칭/표현 | P3 |
| CHG-02 | MVP를 생태계 분석 중심으로 재정의 | 변경 | P0 |
| CHG-03 | 기능 비교·Evidence Drawer를 MVP → 확장으로 이동 | 범위 이동 | P0 |
| CHG-04 | 후보 검색을 semantic-only에서 hybrid reranking 구조로 변경 | 변경/구체화 | P0 |
| CHG-05 | MVP Dependency를 직접 의존만으로 제한 | 변경/범위 이동 | P0 |
| CHG-06 | Version Share를 최신 Snapshot으로 확정 | 변경/구체화 | P1 |
| CHG-07 | MVP PDF를 기능 비교와 분리 | 변경 | P0 |
| CHG-08 | GitHub Community를 실제 논의 중심 3단 구조로 고도화 | 변경/구체화 | P1 |
| CHG-09 | 모바일·반응형 제공 범위 제거, Desktop Web only | 삭제/제외 | P1 |
| CHG-10 | 시스템 아키텍처를 권장안 → 확정안으로 전환 | 변경/구체화 | P0/P2 |
| CHG-11 | EC2 #1 배치 / EC2 #2 서빙 역할 고정 | 신규/구체화 | P2 |
| CHG-12 | 후보 모델 학습·MLflow·ONNX·스왑 사이클 확정 | 신규/구체화 | P2 |
| CHG-13 | 간접·전이 Dependency를 `확장-04`로 명시 | 신규/범위 이동 | P1 |
| CHG-14 | RAG를 기능 비교 확장 기술 방향으로 명시 | 신규/구체화 | P1/P2 |
| CHG-15 | 후보 랭킹 결측 신호를 별도 자료 상태로 관리 | 신규 | P1 |
| CHG-16 | Issues 장기 시계열과 GitHub 논의 보고서를 더 명확히 분리 | 구체화 | P1 |
| CHG-17 | 기능 비교 POC를 MVP 근거가 아닌 확장 참고 자료로 재분류 | 범위 이동 | P2 |
| CHG-18 | 운영·보안·배포 경계를 명시 | 신규/구체화 | P2 |

---

## 2. 0904 기획의 방향성 변화

0904의 변화는 개별 기능 수정이라기보다 세 가지 큰 전략 변화로 묶을 수 있다.

### 2.1 ‘넓은 MVP’에서 ‘검증 가능한 Core MVP’로

0902 MVP는 다음 흐름을 한 번에 완성하려 했다.

`소개 → 패키지 입력 → 후보 선택 → 생태계 변화 → 정확한 버전 기능 비교 → Evidence Drawer → PDF`

0904 MVP는 다음으로 축소된다.

`소개 → 패키지 입력 → 후보 선택 → 직접 의존 생태계 보고서 → PDF`

그리고 아래가 확장으로 이동한다.

- 정확한 버전 기능 비교
- 기능 버전 변경·재분석
- 환경·기능 판정
- Evidence Drawer
- RAG 기반 근거 검색·해설
- GitHub Community
- 간접·전이 Dependency

이 변화는 단순 ‘기능 삭제’가 아니라 **MVP 완료 조건을 핵심 생태계 분석으로 재설계**한 것이다.

### 2.2 ‘설명 유사 후보’에서 ‘현실적인 비교 후보’로

0902의 후보 탐색은 description·keywords의 임베딩과 관련성 정렬이 중심이었다. 후보 카드는 `설명 유사도`, `공통 키워드`, `최근 배포일`을 핵심 근거로 보여줬다.

0904는 후보를 두 단계로 본다.

1. 의미 관련성으로 후보 pool을 넓게 찾는다.
2. 실제 공개 생태계에서 관측된 관계 신호를 사용해 재랭킹한다.

따라서 후보의 의미도 `설명이 비슷한 패키지`에서 **`비교 대상으로 검토할 현실적 관련성이 있는 패키지`**로 바뀐다.

### 2.3 ‘권장 구조’에서 ‘구현 기준’으로

0902 개발 구상안은 특정 기술을 강제하지 않는다고 명시했다. 반면 0904는 다음을 구현 기준으로 고정한다.

- EC2 2대 (`t4g.xlarge`) + 외부 GPU 학습 서버
- EC2 #2: nginx → Spring Boot → PostgreSQL 16
- EC2 #1: cron → Spark → MinIO → Python 유사도 배치 → MLflow → PostgreSQL 적재
- BigQuery deps.dev + npm API
- GitHub Actions → GHCR → EC2 배포
- 외부 인바운드 `#2:443`
- 내부 포트는 사설 IP/Tailscale 제한

즉 0904는 제품 기획과 기술 실행안의 연결 강도가 크게 높아졌다.

---

## 3. 제품 레벨 핵심 변경 상세

## CHG-01. 서비스명 `OSS Shift` → `Pickage`

- **유형**: 명칭/표현
- **중요도**: P3

### 0902

- 문서·Figma 명칭이 `OSS Shift` 기준.
- 서비스 한 문장도 OSS Shift를 주어로 사용.

### 0904

- 네 문서 모두 `Pickage`로 변경.
- Figma 기준도 `Pickage Web Service Wireframe V1`로 정리.
- 서비스 설명도 `오픈소스 자체`보다 `npm 패키지 후보와 생태계 분석`에 초점을 둔다.

### 영향

브랜드 변경 자체는 기능 변경은 아니지만, 0904에서는 서비스 한 문장의 초점도 함께 달라졌기 때문에 단순 rename만으로 보기는 어렵다.

---

## CHG-02. MVP의 핵심 가치 재정의

- **유형**: 변경
- **중요도**: P0

### 0902 MVP

- 서비스 소개
- 패키지 입력
- 관련 후보 선택
- 생태계 변화
- **기능 비교**
- **Evidence Drawer**
- 전체 보고서 PDF

즉 기능 근거 검토까지 MVP에 포함되어 있었다.

### 0904 MVP

- 서비스 소개
- 패키지 입력·존재 확인
- 의미 관련성 + 생태계 신호 기반 후보 선택
- 직접 Dependency
- Downloads
- 직접 의존 기준 유지·유입·이탈
- 최신 Version Share Snapshot
- 생태계 보고서 PDF

### 의미

0904에서 MVP의 성공 기준은 **‘정확한 기능 판정까지 제공했는가’가 아니라 ‘비교 후보를 현실적으로 좁히고 공개 생태계 변화의 핵심을 한 흐름에서 볼 수 있는가’**로 바뀌었다.

### 영향

- 서비스 기획: 서비스 한 문장과 문제 정의 재작성
- IA: MVP 보고서는 1페이지로 완결
- 요구사항: 기능-10~13을 확장으로 재분류
- 개발: 기능 분석 파이프라인을 Core path 밖으로 이동
- PDF: 기능 분석 상태와 생성 조건 분리

---

## CHG-03. 기능 비교·Evidence Drawer의 MVP → 확장 이동

- **유형**: 범위 이동
- **중요도**: P0

### 0902

보고서 2페이지 기능 비교는 MVP였다.

주요 구성:

- 최신 안정 버전 결과
- 핵심 환경·설치 조건
- 핵심 기능 5~7개
- 버전 선택
- 재분석
- GPT형 진행 상태
- 판정
- 중립 해설
- Evidence Drawer

### 0904

기능-10~13 전체가 확장으로 이동한다.

- 기능-10: 기능 버전·근거 수집 [확장]
- 기능-11: 환경·설치 조건 [확장]
- 기능-12: 기능 비교 [확장]
- 기능-13: 근거·해설·Drawer [확장]

### 유지되는 것

범위만 바뀌었지 기존 핵심 계약이 폐기된 것은 아니다.

- 정확한 버전 기준
- 근거 충돌 시 임의 판정 금지
- 재분석 시 이전 정상 결과 보존
- Evidence ID 추적
- 판정과 자료 상태 분리
- Drawer의 근거 노출 계약

### 새로 추가된 것

확장 기술 방향으로 `Data + AI + RAG`를 우선 검토하고 필요 시 `AI + RAG`로 축소하는 경로가 추가된다.

### 해석

따라서 0904를 설명할 때 **“기능 비교 삭제”라고 표현하면 잘못**이다. 정확한 표현은 **“MVP 완료 조건에서 제외하고 확장 기능으로 재배치”**이다.

---

## CHG-04. 후보 검색·정렬의 구조적 변경

- **유형**: 변경 + 구체화
- **중요도**: P0

### 0902

후보 검색 권장 흐름:

1. 입력 패키지 존재 확인
2. 패키지 벡터 조회
3. 유사 후보 검색
4. self/deprecated/plugin·adapter 후보 제외
5. 관련성 기준 정렬
6. 후보 최대 3개 반환
7. 상위 2개 기본 선택

후보 카드에는:

- 패키지명
- 짧은 설명
- 설명 유사도
- 공통 키워드
- 최근 배포일
- 자료 상태

을 제공했다.

### 0904

후보 결정이 명확한 단계형 파이프라인으로 바뀐다.

1. 코퍼스 자격 필터
2. MLflow `@production` 모델 기반 ONNX 임베딩
3. 정규화 벡터 행렬곱으로 top-K 50 생성
4. `score = 0.7·cos + 0.3·move_lift` 기본 재랭킹
5. 대체 이동 쌍·deprecated 지목 가산
6. dependents 교집합 `> 0.3` 보완재 감점
7. 품질 필터 drop
8. `similar_packages`를 model version별 적재
9. `model_production` 포인터 전환
10. 최종 유효 후보 최대 3개만 서빙

### 사용자 화면 변화

0902의 `설명 유사도` 단일 값 중심 표현에서 벗어나:

- 관련성 근거 요약
- 공통 키워드
- 확보 가능한 생태계 신호 요약
- 최근 배포일
- 자료 상태

으로 바뀐다.

내부 계산식과 계수는 사용자에게 품질 점수로 노출하지 않는다.

### 중요한 의미

- semantic similarity는 최종 판단이 아니라 후보 pool 생성 수단이 됨
- 생태계 관측 신호가 reranking에 들어감
- 생성형 AI는 후보 생성·정렬에 계속 사용하지 않음
- 후보 랭킹은 기술 품질 순위가 아니라 **비교 후보 관련성**임

---

## CHG-05. 후보 ranking의 자료 상태 계약 추가

- **유형**: 신규/구체화
- **중요도**: P1

0904에는 후보 ranking 신호가 일부 수집되지 않거나 검증되지 않은 경우를 실제 값 `0`과 구분하는 상태가 추가된다.

새 용어:

- `미검증 신호`: 랭킹에 사용할 신호를 확보하거나 검증하지 못한 상태

요구사항에도 `기능-16-R03B` 형태로 별도 오류/자료 상태가 추가된다.

### 의미

후보 알고리즘이 복합 신호 기반으로 바뀌면서, **신호 결측을 0으로 오해하지 않는 데이터 계약**이 필요해졌다.

---

## CHG-06. Dependency를 MVP Direct only로 제한

- **유형**: 변경 + 범위 이동
- **중요도**: P0

### 0902

Dependency 계약은 전체/특정 버전의 추이를 보여주는 것이 중심이었고, 직접·간접 범위가 MVP 차원에서 강하게 분리되어 있지 않았다.

### 0904

MVP는 **직접 의존 관계만** 분석한다고 명시한다.

- 그래프: 직접 Dependency
- 유지·유입·이탈: 직접 의존 기준
- 버전 필터: 직접 의존 시계열 표시 필터
- 직접/간접 전환 UI 없음

### 간접 의존

간접·전이는 삭제되지 않고 `확장-04`로 신설된다.

- 직접 의존과 합산 금지
- 산출 범위 명시
- 직접/간접 선택 UI가 있으면 현재 범위 명시

### 의미

MVP에서 데이터 규모와 해석 부담을 줄이고, 사용자가 무엇을 보고 있는지 명확하게 만든 변화다.

---

## CHG-07. Version Share를 ‘최신 Snapshot’으로 확정

- **유형**: 변경 + 구체화
- **중요도**: P1

### 0902

Version Share는 공개 의존 조건에서 관측된 버전 계열 비중을 보여주도록 정의되어 있었지만, 명칭만으로는 시계열·현재 분포의 관계를 오해할 여지가 남아 있었다.

### 0904

다음이 명시된다.

- **최신 집계 기준일의 Snapshot 분석**
- Snapshot 기준일 표시
- 시간축 없음
- 과거 비중 연결선 없음
- 실제 설치 버전 아님
- 공개 의존 조건의 버전 계열 분포
- 해석 불가 조건은 별도 표시

### 영향

- 서비스 설명에서 ‘최신 버전 분포’가 핵심 가치로 들어옴
- IA 카드에 Snapshot 기준일 필수
- 요구사항 `기능-17` 완료 기준 변경
- 개발에서 Version Share 처리도 최신 snapshot 집계로 고정
- PDF에 Snapshot 기준일 포함

---

## CHG-08. Activity의 역할 명확화

- **유형**: 구체화
- **중요도**: P1

0902와 0904 모두 MVP Activity의 기본은 Downloads이고 Issues는 확장이다.

0904에서는 더 명확히:

- MVP: Downloads 시계열
- 확장: Issues 시계열
- GitHub Community의 대화/쟁점 구조와 Issue 장기 시계열을 분리

즉 **수치 변화는 Activity**, **현재 논의 맥락은 Community Report**라는 역할 분리가 강화됐다.

---

## CHG-09. PDF 완료 조건을 생태계 결과 중심으로 변경

- **유형**: 변경
- **중요도**: P0

### 0902 PDF 차단 조건

- 기능 비교 버전 변경 후 재분석 미완료
- 재분석 진행 중
- 최초 핵심 결과 없음
- 화면 선택과 완료 분석 버전 불일치

즉 기능 비교 상태가 PDF 생성 가능 여부에 직접 연결돼 있었다.

### 0904 MVP PDF 차단 조건

- 비교 대상 미확정
- 최초 생태계 핵심 결과 미완료
- 필수 ReportSnapshot 생성 불가 오류

다음은 차단하지 않는다.

- 일부 기간 자료 없음
- 일부 직접 Dependency 자료 부족
- Version Share 해석 불가
- 후보 ranking 신호 일부 미검증
- 확장 기능 미완료

### 결과

MVP PDF 기본 구성도 바뀐다.

**0902**

- 생태계 변화
- 기능 비교
- 근거 부록
- GitHub Community(가능 시)

**0904**

- 후보·비교 대상과 분석 범위
- Downloads
- 직접 Dependency + 유지·유입·이탈
- 최신 Version Share Snapshot + 기준일
- 자료 상태·해석 한계

기능 비교·GitHub는 **완료된 확장 결과가 있을 때만** 추가할 수 있다.

---

## CHG-10. GitHub Community 정보 구조 고도화

- **유형**: 변경 + 구체화
- **중요도**: P1

### 0902

상단 요약:

- 최근 릴리스
- 최근 커밋
- 열린 Issue
- 열린 PR

본문:

- 주요 논의
- 사용자/기여자 주장
- 유지관리자 우려
- 재현·검토·구현 작업
- 합의/미합의

### 0904

Figma 최신 구조를 반영해 3단으로 재설계한다.

#### 1단 — 커뮤니티 보고서 요약·수치

- 패키지명
- 검증된 저장소
- 분석 대상 Issue 범위
- 현재 논의 한 문장 요약
- 분석 이슈 수
- 해당 이슈들의 누적 댓글 수
- 사용자 반응 수
- OPEN 상태 수

#### 2단 — 핵심 이슈와 쟁점

- Issue 번호·상태
- 댓글·반응 수
- 제목
- 쟁점 요약
- 실제 댓글 전개 기반 `논의 흐름`

#### 3단 — 실제 논의 흐름

- 작성자
- 검증 가능한 역할
- 실제 댓글 순서
- 핵심 논지 한국어 요약

### 강화된 제약

- 가상 대화 생성 금지
- 역할 임의 부여 금지
- 원문에 없는 합의/단계 생성 금지
- 상단 수치와 하단 대화는 같은 Issue snapshot 사용
- Issue/comment source record 추적 가능
- 일부 댓글 누락/API 제한 시 완전한 논의라고 단정 금지

### 의미

GitHub Community가 **저장소 통계 보조 화면**에서 **실제 논의 맥락을 읽는 커뮤니티 리포트**로 성격이 더 분명해졌다.

---

## CHG-11. Desktop Web only로 제공 범위 고정

- **유형**: 삭제/제외
- **중요도**: P1

### 0902

IA에 명시적인 반응형 계약이 있었다.

- 모바일 후보 카드 1열
- 모바일 비교표 가로 스크롤
- 모바일 Evidence Drawer 전체 높이 하단 시트
- 모바일 PDF 전체 너비 시트
- 모바일 그래프 필터 세로 배치
- 모바일 선택 바 분리

### 0904

- 모든 화면은 데스크톱 컴퓨터 웹 브라우저 기준
- Evidence Drawer는 우측 560px overlay
- PDF 확인은 중앙 modal
- 소형 화면 전용 IA 없음
- 별도 모바일 client state 없음

### 의미

단순 responsive 우선순위 변경이 아니라 **제품 제공 범위에서 모바일 설계를 제거**한 것이다.

---

## CHG-12. 개발 문서의 성격: 권장 구조 → 시스템 확정안

- **유형**: 변경
- **중요도**: P0/P2

### 0902

개발 구상안 서두:

- 특정 framework/provider를 강제하지 않음
- `제품 계약 / 권장 구조 / 실험 필요` 구분
- 시스템 구조는 논리 흐름 중심

### 0904

- `시스템 확정안 / 제품 계약 / 튜닝 가능`으로 재분류
- 서버·배치·저장·모델·배포 구조와 주요 기술 stack을 구현 기준으로 고정

### 의미

0902의 “이런 방향으로 구현하면 좋다”에서 0904의 “v1은 이 구조로 구현한다”로 바뀌었다.

---

## CHG-13. v1 인프라 경계 확정

- **유형**: 신규/구체화
- **중요도**: P2

0904에 추가된 주요 인프라 계약:

### EC2 #2 — Serving

- `t4g.xlarge`
- nginx
- Spring Boot WAS
- PostgreSQL 16
- Spark worker②는 배치 시에만 사용
- 사용자 외부 인바운드는 HTTPS 443

### EC2 #1 — Batch / Model Ops

- `t4g.xlarge`
- cron
- Spark master + worker①
- MinIO on EBS 200GB
- Python 유사도 배치
- MLflow Registry
- PostgreSQL 적재 스크립트

### External

- BigQuery deps.dev snapshot
- npm API downloads·packument
- GPU server / JupyterLab
- GitHub Actions
- GHCR

### 관리형 서비스 경계

권한 제약으로 AWS 관리형 서비스 대신 EC2/EBS 기반 self-hosting을 사용한다.

---

## CHG-14. 후보 모델 라이프사이클 추가

- **유형**: 신규/구체화
- **중요도**: P2

0904에서는 후보 랭킹이 단순 배치 코드가 아니라 모델 버전 관리 사이클을 가진다.

1. Spark S7이 training pair 갱신
2. 외부 GPU가 MinIO에서 학습쌍 read-only pull
3. GPU에서 학습 후 ONNX를 MLflow에 등록
4. EC2 #1 평가 배치가 Recall@10·MRR 등 개선 확인
5. candidate로 전수 임베딩
6. `similar_packages(vN+1)` 병렬 적재
7. shadow 비교
8. `@production` alias + `model_production` pointer 변경
9. rollback도 pointer 변경으로 처리

### 의미

후보 결과는 사용자 요청 시 모델 추론하지 않고 **사전 계산된 결과**를 PostgreSQL에서 읽는다.

---

## CHG-15. 저장 계층 역할 구체화

- **유형**: 구체화
- **중요도**: P2

### 0902

- 서비스 조회 저장소
- 기능 분석 캐시
- SourceSnapshot/AnalysisRun 등 논리 엔터티
- 장기 저장/미보관 기준

### 0904

저장 역할이 실제 제품별로 분리된다.

#### PostgreSQL 16

- 생태계 최종 집계
- 후보 `similar_packages`
- `model_production` pointer
- model/MLflow metadata 일부
- 서빙 API의 주 조회 원장

#### MinIO

- batch raw/curated 자료
- training pairs
- package vectors
- MLflow artifacts

### 중요한 변화

Spring Boot는 사용자 요청 시 MinIO나 모델을 직접 조회하지 않고 **PostgreSQL 사전 결과 중심으로 서빙**한다.

---

## CHG-16. RAG를 기능 비교 확장 구조로 도입

- **유형**: 신규/구체화
- **중요도**: P1/P2

### 0902

기능 비교는 Registry·tarball·docs를 수집하고 구조화 근거와 Evidence ID를 AI에 주는 정적 분석 중심 설계였다.

### 0904

확장 구현 경로가 두 가지로 정의된다.

**우선 경로**

`구조화 Data + AI + RAG`

**Fallback**

`AI + RAG`

### 유지되는 핵심 안전 계약

- 정확한 package version 기준
- 전체 문서를 무제한 AI 입력으로 전달하지 않음
- 검색된 근거만 LLM에 제공
- Evidence ID 또는 동등 식별자 연결
- 근거 없는 기능 생성 금지
- 충돌 근거 임의 선택 금지

### 아직 확정되지 않은 것

0904 문서 자체에서는 다음 세부 stack을 고정하지 않는다.

- LLM provider/model
- embedding model
- vector DB / pgvector 여부
- chunking 방식
- reranker
- LangChain/LlamaIndex 등 framework

즉 **RAG 도입 방향은 결정됐지만 세부 구현 stack은 미확정**이다.

---

## CHG-17. 간접·전이 Dependency `확장-04` 신규

- **유형**: 신규 + 범위 이동
- **중요도**: P1

0904에서 기존 기능 ID를 재번호화하지 않고 신규 확장 ID를 추가한다.

`확장-04 간접·전이 Dependency`

이를 통해 기존 `기능-07 Dependency`의 MVP 계약을 직접 의존으로 좁히면서도 미래 확장 가능성을 문서상 유지한다.

---

## CHG-18. 운영·보안·배포 기준 추가

- **유형**: 신규/구체화
- **중요도**: P2

0904에 추가된 대표 계약:

- 외부 인바운드: `#2:443` only
- SSH 22: 관리 IP + Actions
- PostgreSQL 5432 / MinIO 9000 / Spark 7077+dynamic / MLflow 5000: 사설 IP + Tailscale
- GPU: MinIO curated read-only / MLflow register only
- production 승격 token은 EC2 #1에만
- BigQuery service account key는 #1만 보유
- GitHub Actions test/build
- GHCR image pull
- Flyway migration

v1에서 제외:

- Prometheus/Grafana/healthchecks stack
- RAG service + external LLM (기능 확장 시)
- History Server
- blue-green
- Redis
- Loki

---

## 4. 사용자 여정 Before / After

### 4.1 0902

```text
서비스 소개
  ↓
패키지 입력
  ↓
후보 선택
  ↓
보고서 1: 생태계 변화
  ↓
보고서 2: 기능 비교
  ↓
Evidence Drawer / 재분석
  ↓
전체 보고서 PDF

[확장]
GitHub Community
```

### 4.2 0904

```text
서비스 소개
  ↓
패키지 입력
  ↓
후보 ranking 기반 후보 선택
  ↓
보고서 1: 직접 의존 생태계 변화
  ↓
생태계 ReportSnapshot
  ↓
PDF

[확장]
├─ 기능 비교 + RAG + Evidence Drawer
├─ GitHub Community
├─ Issues 시계열
├─ 버전 고착 심화
├─ 관측된 교체 흐름
└─ 간접·전이 Dependency
```

### 4.3 UX 관점에서 실제로 달라진 점

| 지점 | 0902 | 0904 |
|---|---|---|
| 후보를 보는 기준 | 의미 유사성 중심 | 의미 후보 + 생태계 관계 신호 |
| 보고서 첫 진입 | 생태계 후 기능 비교까지 MVP | 생태계 보고서만 MVP 필수 |
| Dependency | 범위 설명 중심 | 직접 의존만 명시 |
| Version Share | 버전 계열 비중 | 최신 Snapshot + 기준일 |
| 기능 비교 | 기본 보고서 탭 | 제공 시에만 확장 탭 |
| PDF | 기능 비교 상태에 종속 | 생태계만으로 완료 가능 |
| 모바일 | responsive 계약 존재 | 제공 범위 제외 |

---

## 5. MVP / Extension 범위 비교

| 영역 | 0902 | 0904 | 변화 |
|---|---|---|---|
| 서비스 소개 | MVP | MVP | 유지 |
| 패키지 입력 | MVP | MVP | 유지 |
| 후보 선택 | MVP | MVP | 알고리즘 강화 |
| 후보 semantic retrieval | MVP | MVP | 유지 |
| 후보 ecosystem reranking | 미구체화 | MVP | 신규/구체화 |
| 직접 Dependency | MVP | MVP | 범위 명확화 |
| 간접·전이 Dependency | 명시적 분리 약함 | 확장-04 | 확장 분리 |
| Downloads | MVP | MVP | 유지 |
| 유지·유입·이탈 | MVP | MVP | 직접 의존으로 한정 |
| Version Share | MVP | MVP | Snapshot으로 확정 |
| Issues 시계열 | 확장 | 확장 | 유지/역할 명확화 |
| 기능 비교 | **MVP** | **확장** | 핵심 Scope 이동 |
| 기능 비교 재분석 | MVP | 확장 | Scope 이동 |
| Evidence Drawer | MVP | 확장 | Scope 이동 |
| 기능 비교 RAG | 없음/구조화 AI 중심 | 확장 | 신규 방향 |
| GitHub Community | 확장 | 확장 | UX 고도화 |
| PDF | 생태계+기능 중심 | 생태계 기본 | 완료 조건 변경 |
| Desktop Web | desktop+mobile responsive | desktop only | 모바일 제거 |

---

## 6. 기능 ID별 변경 매트릭스

기존 기능 번호를 최대한 유지하면서 Scope와 계약을 변경한 것이 0904의 특징이다.

| 기능 ID | 0902 | 0904 | 변경 유형 |
|---|---|---|---|
| 기능-01 패키지 입력 | npm 패키지 입력 | 동일 | 유지 |
| 기능-02 존재 확인 | npm 존재 검증 | 동일 | 유지 |
| 기능-03 후보 제공 | 의미/설명 유사 후보 | semantic pool + ecosystem reranking | 핵심 변경 |
| 기능-04 비교 대상 확정 | 기준 포함 최대 3개 | 동일, 직접 추가가 ranking 변경하지 않음 명확화 | 구체화 |
| 기능-05 기간·기준일 | 보고서 공통 | 생태계 기준일 중심, 기능 버전은 확장 | 범위 조정 |
| 기능-06 Downloads | MVP | MVP | 유지 |
| 기능-07 Dependency | Dependency | **MVP 직접 의존 only** | 범위 축소 |
| 기능-08 유지·유입·이탈 | Dependency 변화 | **직접 의존 기준** | 의미 구체화 |
| 기능-09 생태계 통합 | Dependency/Activity/Share | direct Dependency/Downloads/Snapshot | 변경 |
| 기능-10 기능 버전·근거 수집 | MVP | 확장 | Scope 이동 |
| 기능-11 환경·설치 조건 | MVP | 확장 | Scope 이동 |
| 기능-12 기능 비교 | MVP | 확장 | Scope 이동 |
| 기능-13 근거·해설·Drawer | MVP | 확장 | Scope 이동 |
| 기능-14 PDF | 전체 보고서 | MVP 생태계 보고서, 확장은 완료 시 추가 | 완료 기준 변경 |
| 기능-15 서비스 소개 | MVP | MVP | 유지, 메시지 변경 |
| 기능-16 상태·오류 | 기능 분석 상태 포함 | 후보 신호 결측·생태계 상태 중심 + 확장 오류 분리 | 확장 |
| 기능-17 Version Share | 버전 계열 비중 | 최신 Snapshot | 의미 확정 |
| 확장-01 버전 고착 | 확장 | 확장 | 유지, Snapshot 뒤 심화로 명확화 |
| 확장-02 교체 흐름 | 확장 | 확장 | 유지 |
| 확장-03 Issues/GitHub | 확장 | 확장 | Community 계약 대폭 고도화 |
| 확장-04 간접·전이 Dependency | 없음 | 신규 | 신규 |

---

## 7. 서비스 기획서 상세 비교

### 7.1 서비스 한 문장

**0902**

- 관련 후보 발견
- 생태계 변화
- 정확한 버전 기능 차이
- 근거가 연결된 보고서

**0904**

- 의미 관련성 + 공개 생태계 신호 기반 후보
- 직접 의존 관계 변화
- 다운로드 추이
- 최신 Version Share Snapshot

기능 비교는 한 문장 핵심 가치에서 빠지고 확장 설명으로 이동한다.

### 7.2 문제 정의

0902 문제:

- 후보 탐색 분산
- 버전을 너무 일찍 요구
- 수치와 기능 분리
- 최신/과거 문서 혼용
- 고정 기능표
- 근거 재검토 부담
- 커뮤니티 숫자 중심

0904 문제:

- 후보 탐색 분산
- 의미 유사도만으로 후보 선택 위험
- popularity만으로 후보 선택 위험
- 직접/간접 의존 범위 복잡
- Snapshot/시계열 혼동
- 공개 수치의 의미 오해
- 공유 문서 재작성

### 해석

문제의 중심이 **기능 판정 신뢰성 문제**에서 **후보 현실성 + 생태계 데이터 해석 문제**로 이동한다.

### 7.3 제공 가치

0902:

- 정확한 버전 기능 판단
- Evidence Drawer
- 글 중심 community

0904:

- semantic + ecosystem 후보
- Direct Dependency로 단순화
- Version Share Snapshot
- 기능 비교는 RAG 확장

### 7.4 서비스 구조

0902 MVP에 있던 기능 비교가 0904 확장으로 이동한 것이 가장 큰 구조 변화다.

### 7.5 후보 UX

0902:

- 설명 유사도 표시
- 공통 keyword

0904:

- 내부 단일 score 비노출
- 관련성 근거 요약
- 생태계 signal 요약
- 기술 품질 점수로 보이지 않도록 설계

### 7.6 생태계 페이지

- Dependency → Direct Dependency
- Version Share → Latest Snapshot
- Activity → Downloads MVP / Issues extension 유지

### 7.7 AI 역할

0902:

- 후보 단계 생성 AI 금지
- 기능 단계 구조화 근거 기반 설명

0904:

- 후보 단계는 v1 deterministic/hybrid ranker로 더 구체화
- 기능 비교 확장은 RAG retrieval + 선택적 structured data + AI

### 7.8 MVP 완료 범위

0902 포함 목록에 있던 아래 항목들이 0904 `제외 또는 확장`으로 이동한다.

- 최신 안정 버전 기능 결과
- 핵심 환경·기능 표
- 기능 버전 변경·재분석
- 중립 해설
- Evidence Drawer

---

## 8. 메뉴구조 IA 상세 비교

### 8.1 IA 적용 원칙

0902:

- 생태계 변화 + 기능 비교를 같은 보고서 구조의 MVP로 봄
- Dependency 표시 버전과 기능 버전 각각 배치
- Evidence Drawer 기본 구조
- responsive/mobile 계약 존재

0904:

- desktop browser only
- 후보 ranking 정보 표현 계약 추가
- MVP 보고서 1페이지 완결
- Direct Dependency only
- Version Share Snapshot 기준일
- 기능 비교/Drawer 확장
- 생태계 PDF만으로 생성

### 8.2 전체 화면 계층

0902:

```text
보고서
├─ 생태계 변화
├─ 기능 비교
├─ GitHub Community [확장]
└─ PDF
```

0904:

```text
보고서
├─ 생태계 변화 [MVP]
├─ 기능 비교 [확장]
├─ GitHub Community [확장]
└─ PDF
```

즉 화면 명칭은 많이 유지하지만 **접근 가능 조건과 제품 Scope가 바뀐다.**

### 8.3 후보 카드 IA

0904에서 내부 scoring 숫자를 사용자에게 ‘품질 점수’처럼 보여주지 않는 원칙이 강화된다.

### 8.4 생태계 카드

- Dependency에 `직접 의존` 표시
- direct/indirect switch 없음
- Version Share에 Snapshot date
- 시계열 UI 없음

### 8.5 기능 비교 UI

구조 자체는 상당 부분 유지되나 모두 `[확장]`으로 표기된다.

### 8.6 Evidence Drawer

0902:

- Desktop: 우측 560px overlay
- Mobile: full-height bottom sheet

0904:

- Desktop 560px overlay만 기준
- mobile layout 제거

### 8.7 GitHub Community

0902 IA의 ‘논의 항목’ 중심 단순 구조에서 0904는 별도 하위 section 4개로 세분화된다.

- 상단 보고서 요약
- 핵심 이슈와 쟁점
- 실제 논의 흐름
- 패키지·저장소 전환과 예외

### 8.8 responsive 기준

0902의 `## 13. 반응형 기준`이 0904에서 `## 13. 데스크톱 웹 화면 기준`으로 대체된다.

---

## 9. 요구사항 명세서 상세 비교

### 9.1 서비스 대상 정의

0902 대상:

`후보 발견·생태계 변화·정확한 버전 기능 근거 비교 서비스`

0904 대상:

`후보 발견·직접 의존 관계·Downloads·최신 Version Share Snapshot 분석 서비스`

요구사항 문서의 첫 줄부터 MVP 정의가 달라진다.

### 9.2 적용 원칙 확대

0904에 새로 명시된 핵심 원칙:

- desktop web only
- 의미 유사도/popularity 단일 지표로 후보 결정 금지
- v1 ranking 계산식은 개발 구상안에 귀속
- Direct Dependency only
- Version Share Snapshot
- ranking signal 미검증 상태
- 기능 비교는 제공 시 근거 충돌 규칙 적용

### 9.3 공통 용어

신규/변경 용어:

- 후보 ranking
- Version Share Snapshot
- 미검증 신호
- 기능 비교 버전 [확장]
- Evidence Drawer [확장]

### 9.4 후보 요구사항

0902의 `설명 유사도 + keyword` 계약에서 0904는 `관련성 근거 + 생태계 신호 상태`로 변경된다.

### 9.5 Dependency 요구사항

0904 `기능-07-R01`:

- 분석 범위를 `직접 의존`으로 명시
- direct/indirect switch 없음

`확장-04-R01`:

- indirect/transitive는 별도 확장

### 9.6 Version Share 요구사항

0904에서는:

- Snapshot date 필수
- time axis 금지
- 실제 설치 버전으로 명명 금지

### 9.7 기능 비교 요구사항

전체 요구사항 구조는 유지하지만 섹션 제목부터 `확장:`으로 변경된다.

### 9.8 GitHub Community 요구사항 증가

0902는 R01~R09 수준의 repository/summary/discussion 계약이었다.

0904는 R01~R14로 확장되고 다음이 추가된다.

- 분석 Issue set 정의
- summary metric 동일 snapshot
- 논의 흐름 단계
- 실제 comment conversation
- author role 검증
- Korean summary fidelity
- source record traceability
- snapshot consistency

### 9.9 PDF 요구사항

0902 `기능-14-R03`:

- 기능 버전·마지막 완료 분석 포함

0904:

- 생태계 기간
- Direct Dependency filter
- Version Share date
- last completed ecosystem result

으로 기준이 바뀐다.

### 9.10 제공하지 않는 기능

0904에서는 `MVP에서 제공하지 않음`과 `서비스 전체에서 제공하지 않음`을 분리한다.

이는 기능 비교처럼 **‘지금은 MVP 밖이지만 미래에 제공’**할 항목과 **‘제품 철학상 제공하지 않음’**을 구별하기 위함이다.

---

## 10. 기능별 개발 구상안 상세 비교

개발 구상안은 4개 문서 중 가장 큰 변화가 있다.

### 10.1 문서의 기술 결정 수준

0902:

- 권장 구조
- 실험 필요
- framework/provider 비강제

0904:

- 시스템 확정안
- 제품 계약
- 튜닝 가능

### 10.2 처리 구조

0902:

| 영역 | 처리 |
|---|---|
| 후보 | 사전 색인·로컬 검색 |
| 생태계 | batch/precompute |
| 기능 비교 | 최초 요청 분석 + cache |
| GitHub | TTL cache |
| PDF | snapshot |

0904:

| 영역 | 처리 |
|---|---|
| 후보 | batch embedding + top-K 50 + reranking → PostgreSQL |
| 생태계 | BigQuery/npm → EC2 #1 batch |
| 보고서 | Spark S1~S7 → PostgreSQL |
| Downloads | 독립 cron |
| Version Share | latest snapshot |
| 기능 비교 | Data+AI+RAG / AI+RAG [확장] |
| PDF | ecosystem ReportSnapshot |

### 10.3 시스템 아키텍처

0902 논리 흐름:

`deps.dev/npm → index/aggregate → service store → web report`

`selected packages → exact-version analysis → evidence/cache → web report`

0904 물리 구조:

`User → HTTPS 443 → nginx(#2) → Spring Boot(#2) → PostgreSQL(#2)`

`BigQuery/npm → cron(#1) → Spark(#1+#2 worker) → MinIO(#1) → batch → PostgreSQL(#2)`

`GPU → MinIO training_pairs → MLflow model registration`

`GitHub → Actions → GHCR → EC2`

### 10.4 후보 알고리즘

0902:

- embedding/search
- basic filtering
- relevance order
- threshold 실험

0904:

- eligibility filter
- MLflow production model
- ONNX CPU embedding
- top-K 50
- `0.7 cos + 0.3 move_lift`
- bonus / penalty / drop
- model-versioned `similar_packages`
- production pointer switch

### 10.5 기능 분석

0902의 FeatureAssessment/EvidenceRecord/AnalysisRun 구조는 상당 부분 보존된다.

0904에서는 섹션 전체가 `[확장]`으로 재분류되고 RAG retrieval 단계가 추가된다.

### 10.6 GitHub 데이터 계약

0902:

- Activity Issues
- Community summary/discussion

0904:

- `CommunitySummary`
- `CommunityTopic`
- `DiscussionMessage`
- `communitySnapshotId` 동일성
- partial/fetch-limited 상태

### 10.7 저장/캐시

0902는 cache key와 보관 정책 중심이다.

0904는 실제 storage role을 확정한다.

- PostgreSQL 16 = serving ledger
- MinIO = batch/model state
- MLflow = model registry
- model/version consistency rule

### 10.8 운영

0904 신규:

- monitoring stack은 v1 제외
- Slack/Discord webhook 최소 안전선
- downloads 수집 실패 중요도 강조
- docker logs 의존

### 10.9 POC 위치 변경

0902의 POC는 기능 비교 MVP의 개발 가능성을 뒷받침하는 장이었다.

0904에서는 제목부터:

`실제 POC 검증 결과 [기능 비교 확장 참고]`

로 바뀐다.

즉 POC 내용은 버리지 않고 **확장 기술 가능성 참고 자료**로 보존한다.

---

## 11. 데이터·기술 아키텍처 변화 요약

### 11.1 0902

```text
External Data
   ↓
Precompute / Index
   ↓
Service Store
   ↓
Web Report

Selected package/version
   ↓
Analysis Workers
   ↓
Evidence / Assessment Cache
   ↓
Feature Report
```

### 11.2 0904

```text
                    ┌──────── BigQuery deps.dev
                    │
                    ├──────── npm API
                    ▼
             EC2 #1 Batch/Model
       cron → Spark → MinIO → Python ranker
                  │          ↓
                  │        MLflow
                  │
                  └───────────────┐
                                  ▼
User → nginx → Spring Boot → PostgreSQL 16
          EC2 #2          ↑
                         staging/swap

External GPU
   ├─ training_pairs pull from MinIO
   └─ ONNX register to MLflow

GitHub Actions → GHCR → EC2 #1/#2
```

### 11.3 기술적으로 새로 확정된 핵심

- 사전 계산 후보 서빙
- model registry/alias
- ONNX CPU inference
- Spark multi-worker
- MinIO self-hosted object storage
- PostgreSQL 16 serving ledger
- table swap deployment for batch results
- deployment lane
- network/security boundary

---

## 12. 삭제 / 이동 / 신규 항목 정리

### 12.1 실제 제공 범위에서 삭제

- 모바일 전용 layout
- 모바일 Evidence bottom sheet
- 모바일 PDF sheet
- responsive breakpoint별 IA
- 별도 small-screen client layer

### 12.2 MVP에서 확장으로 이동

- 기능 비교
- 기능 비교 version selection
- 재분석
- FeatureAssessment
- Evidence Drawer
- 기능 비교 narrative
- 정확한 버전 RAG/AI 분석
- 간접·전이 Dependency

### 12.3 신규

- Pickage brand
- 후보 ecosystem reranking
- `move_lift`
- top-K 50
- v1 ranking formula
- `similar_packages` versioned swap
- `model_production`
- external GPU training loop
- MLflow model registry
- EC2 2-node architecture
- `확장-04`
- GitHub Community 3-layer data contract
- Desktop Web only product boundary

### 12.4 유지되지만 의미가 구체화

- Version Share → Snapshot
- Activity → Downloads MVP / Issues extension
- 후보 최대 3개 / 상위 2개 기본 선택
- PDF ReportSnapshot 재사용
- 자료 없음/부분/오류 분리
- final recommendation 금지
- arbitrary package execution 금지

---

## 13. 4개 문서 교차 정합성 검증

| 제품 결정 | 서비스 | IA | 요구사항 | 개발 | 결과 |
|---|---:|---:|---:|---:|---|
| Pickage 명칭 | ✓ | ✓ | ✓ | ✓ | 일치 |
| MVP 생태계 중심 | ✓ | ✓ | ✓ | ✓ | 일치 |
| 기능 비교 확장 이동 | ✓ | ✓ | ✓ | ✓ | 일치 |
| 후보 hybrid ranking | ✓ | ✓ | ✓ | ✓ | 일치 |
| ranking score UI 비노출 | ✓ | ✓ | ✓ | ✓ | 일치 |
| Direct Dependency only | ✓ | ✓ | ✓ | ✓ | 일치 |
| indirect/transitive 확장 | ✓ | ✓ | ✓ | ✓ | 일치 |
| Version Share Snapshot | ✓ | ✓ | ✓ | ✓ | 일치 |
| PDF ecosystem-only 완료 | ✓ | ✓ | ✓ | ✓ | 일치 |
| GitHub 3단 구조 | ✓ | ✓ | ✓ | ✓ | 일치 |
| Desktop Web only | ✓ | ✓ | ✓ | ✓ | 일치 |
| v1 architecture fixed | 개념 영향 | 화면 영향 | 요구 영향 | 상세 | 역할에 맞게 일치 |
| RAG는 기능 비교 확장 | ✓ | ✓ | ✓ | ✓ | 일치 |

### 13.1 정합성이 잘 유지된 부분

가장 큰 Scope 변경인 기능 비교 이동이 네 문서에 모두 반영되어 있다.

- 서비스: MVP 목록에서 제거, 확장에 추가
- IA: 보고서 2페이지 `[확장]`
- 요구사항: 기능-10~13 `[확장]`
- 개발: 6~11장 `[확장]`, RAG 구조 추가

Direct Dependency와 Version Share Snapshot도 네 문서가 같은 해석을 사용한다.

### 13.2 문서 역할상 의도적으로 상세 수준이 다른 부분

시스템 아키텍처의 EC2/MinIO/MLflow 같은 구체 기술은 서비스·IA·요구사항에 그대로 복제하지 않는다. 이는 누락이 아니라 정상적인 책임 분리다.

---

## 14. 0904로 인해 실제로 달라지는 작업

### 14.1 Product / 기획

- 기능 비교를 4주 MVP 완료 기준에서 제거
- 후보 알고리즘을 핵심 제품 로직으로 관리
- Direct Dependency 해석 문구 강화
- Snapshot/시계열 용어 엄격 분리
- 확장 기능의 제공 여부를 별도 roadmap으로 관리

### 14.2 Design / Figma

- 기능 비교를 MVP 필수 tab처럼 보이지 않게 처리
- GitHub Community를 3단 리포트 구조로 구성
- mobile responsive 별도 화면 불필요
- candidate card의 단일 유사도 score 중심 표현 제거
- Version Share에 snapshot date 명확히 노출

### 14.3 Frontend

- desktop web only
- candidate ranking result/state 표시
- direct dependency filter
- Version Share no-time-axis
- extension route/tab conditional rendering
- PDF eligibility는 ecosystem state 기준

### 14.4 Backend

- Spring Boot는 precomputed PostgreSQL 조회 중심
- request-time candidate model inference 제거
- report state와 extension state 분리
- PDF snapshot과 feature analysis run coupling 제거

### 14.5 Data / ML

- candidate eligibility filter
- embedding batch
- move_lift/replacement signal
- top-K 50
- reranking
- similar package model versioning
- production pointer
- Spark batch + MinIO

### 14.6 AI / RAG

MVP 차단 요소가 아니다.

추후 기능 비교 확장에서:

- evidence retrieval
- version-scoped corpus
- structured evidence
- LLM explanation
- evidence traceability

을 구현한다.

### 14.7 QA

0902에서 기능 비교 재분석·Drawer가 MVP 필수 테스트였다면, 0904 MVP QA 우선순위는 다음으로 바뀐다.

1. 후보 ranking 결과/결측
2. 최대 3개 선택
3. Direct Dependency
4. 유지·유입·이탈
5. Downloads
6. Version Share Snapshot
7. ecosystem PDF
8. batch/model version consistency
9. deployment/network boundary

기능 비교/RAG/GitHub 상세 QA는 확장 시나리오로 분리된다.

---

## 15. 현재도 미확정 또는 튜닝 가능한 항목

0904가 ‘최종본’이어도 모든 수치·기술이 같은 수준으로 고정된 것은 아니다.

### 15.1 v1에서 구조적으로 확정된 것

- candidate pipeline 단계
- top-K 50
- `0.7*cos + 0.3*move_lift` 기본 score
- complement penalty 개념
- model version/pointer 방식
- EC2 #1/#2 역할
- PostgreSQL/MinIO/MLflow/Spark/nginx/Spring Boot 중심 구조
- Direct Dependency MVP
- Version Share Snapshot
- Desktop Web only
- ecosystem-only PDF eligibility

### 15.2 튜닝 가능

- dependents eligibility 하한
- 일부 bonus/penalty 크기
- 품질 filter threshold
- batch resource/partition 수
- cron 세부 주기
- signal이 늘었을 때 GBDT LTR 전환 시점

### 15.3 방향은 정해졌지만 기술 stack은 미확정

RAG 확장:

- LLM provider/model
- embedding model
- vector store
- hybrid retrieval 세부 방식
- chunking
- reranker
- RAG framework

### 15.4 확장 구현 여부/시점

- 기능 비교
- GitHub Community
- indirect/transitive Dependency
- Issues 시계열
- version stickiness
- observed replacement flow

---

## 16. 0902 → 0904 변경의 제품적 의미

0904는 0902에서 시도했던 기능을 단순히 줄인 것이 아니다. **MVP에서 무엇을 검증해야 하는지 순서를 다시 잡은 버전**이다.

0902의 핵심 질문은 상대적으로 다음에 가까웠다.

> “관련 후보와 생태계 수치뿐 아니라 정확한 버전 기능 근거까지 한 번에 비교할 수 있는가?”

0904의 핵심 질문은 다음으로 좁혀졌다.

> “현재 검토하는 패키지와 실제로 함께 비교할 가치가 있는 후보를 찾고, 직접 의존 관계·Downloads·최신 버전 분포를 통해 선택 리스크를 더 잘 이해할 수 있는가?”

그리고 이 core value가 검증된 다음에:

- 정확한 version-level feature evidence
- RAG
- GitHub community discussion
- indirect dependency

를 붙이는 구조다.

따라서 0904의 가장 중요한 변화는 **기능 수 감소가 아니라 제품 검증 순서의 재설계**라고 해석하는 것이 가장 정확하다.

---

## 17. 최종 결론

0902 대비 0904에서 가장 중요한 변화는 다음 다섯 문장으로 압축할 수 있다.

1. **브랜드가 Pickage로 확정되고, 제품 핵심은 ‘현실적인 비교 후보 + 공개 생태계 분석’으로 선명해졌다.**
2. **정확한 버전 기능 비교·Evidence Drawer는 폐기되지 않았지만 MVP에서 확장으로 이동했다.**
3. **후보 추천은 semantic similarity 중심에서 실제 생태계 관계를 반영하는 v1 reranker로 발전했다.**
4. **MVP 데이터 범위는 Direct Dependency + Downloads + Latest Version Share Snapshot으로 좁혀져 해석과 개발 경계가 명확해졌다.**
5. **기술 문서는 추상적인 권장안에서 EC2 2대·Spark·MinIO·MLflow·PostgreSQL·ONNX를 포함한 실제 v1 시스템 확정안으로 구체화되었다.**

결과적으로 0904는 0902의 ‘더 많은 기능을 한 번에 제공하는 MVP’에서 **핵심 데이터 가치와 실제 구현 가능성을 우선 검증하는 더 좁고 실행 가능한 MVP**로 바뀐 문서 세트다.

---

# Appendix A. 섹션 대응표

## A.1 서비스 기획서

| 0902 | 0904 | 상태 |
|---|---|---|
| §1 한눈에 보는 결론 | §1 동일 | 메시지 변경 |
| §2 문제와 기회 | §2 동일 | 문제 정의 변경 |
| §5 서비스 구조 | §5 동일 | MVP/확장 대폭 변경 |
| §6.3 후보 선택 | §6.3 후보 선택 | ranking 원칙 추가 |
| §7 생태계 변화 | §7 동일 | Direct/Snapshot 구체화 |
| §8 기능 비교 | §8 확장: 기능 비교 | Scope 이동 |
| §9 Evidence Drawer | §9 확장: Drawer | Scope 이동 |
| §10 GitHub Community | §10 GitHub Community | 3단 구조 고도화 |
| §11 PDF | §11 PDF | eligibility 변경 |
| §13 AI 역할 | §13 AI 역할 | ranking/RAG 계약 추가 |
| §14 MVP 완료 범위 | §14 동일 | 범위 재정의 |

## A.2 IA

| 0902 | 0904 | 상태 |
|---|---|---|
| §1 IA 원칙 | §1 IA 원칙 | desktop/ranking/scope 변경 |
| §3 계층 | §3 계층 | 기능 비교 확장 표시 |
| §8 생태계 | §8 생태계 | Direct/Snapshot |
| §9 기능 비교 | §9 확장 화면 | Scope 이동 |
| §10 Drawer | §10 확장 화면 | Scope 이동/mobile 제거 |
| §11 GitHub | §11 GitHub | 3단 구조 |
| §12 PDF | §12 PDF | ecosystem eligibility |
| §13 반응형 | §13 데스크톱 웹 기준 | 제공 범위 변경 |

## A.3 요구사항

| 0902 | 0904 | 상태 |
|---|---|---|
| §1 Scope | §1 Scope | MVP 재정의 |
| §7 후보 | §7 후보 | ranking contract |
| §9 생태계 | §9 생태계 | Direct/Snapshot |
| §10 기능 비교 | §10 확장 | Scope 이동 |
| §11 Drawer | §11 확장 | Scope 이동 |
| §12.1 GitHub | §12.1 GitHub | R01~R14 고도화 |
| 없음 | §12.4 간접 Dependency | 신규 |
| §13 PDF | §13 PDF | eligibility 변경 |
| §15 제공하지 않는 기능 | §15 2분류 | MVP/전체 비제공 분리 |

## A.4 개발 구상안

| 0902 | 0904 | 상태 |
|---|---|---|
| §3 권장 전체 구조 | §3 시스템 아키텍처 확정안 | 대폭 변경 |
| §4 후보 검색 | §4 후보 검색 | model lifecycle/reranking |
| §5 보고서 1 | §5 동일 | Direct/Snapshot |
| §6~11 기능 비교 | §6~11 확장 | RAG + Scope 이동 |
| §12 GitHub | §12 GitHub | 3개 data contract |
| 없음 | §12.5 indirect Dependency | 신규 |
| §13 PDF | §13 PDF | ecosystem snapshot 중심 |
| §14 캐시와 저장 | §14 저장·상태·캐시 확정 | physical storage 역할 확정 |
| §15 비용 | §15 운영·비용 | monitoring/alert 운영 추가 |
| §16 POC | §16 확장 참고 | 의미 재분류 |
| §18 시험 | §18 MVP/확장 분리 | QA Scope 변경 |

---

# Appendix B. 변경 ID 전체 목록

| ID | 변경 | 핵심 영향 문서 |
|---|---|---|
| CHG-01 | Pickage 브랜드 | 전체 |
| CHG-02 | MVP 생태계 중심 | 전체 |
| CHG-03 | 기능 비교 확장 이동 | 전체 |
| CHG-04 | hybrid candidate ranking | 전체 |
| CHG-05 | ranking signal 상태 | 서비스/요구/개발 |
| CHG-06 | Direct Dependency only | 전체 |
| CHG-07 | Version Share Snapshot | 전체 |
| CHG-08 | Activity/Issues 역할 | 서비스/IA/요구/개발 |
| CHG-09 | ecosystem-only PDF | 전체 |
| CHG-10 | GitHub 3단 구조 | 전체 |
| CHG-11 | Desktop Web only | 전체 |
| CHG-12 | 시스템 확정안 | 개발 중심 |
| CHG-13 | EC2 #1/#2 역할 | 개발 |
| CHG-14 | model lifecycle | 개발/후보 정책 |
| CHG-15 | storage 역할 | 개발 |
| CHG-16 | RAG 확장 | 서비스/IA/요구/개발 |
| CHG-17 | 확장-04 indirect | 전체 |
| CHG-18 | 운영·보안·배포 | 개발 |
