# ai — Pickage 유사 패키지 후보 모델

기준 패키지의 `description + keywords` 임베딩으로 **유사/대체 후보 최대 3개**를 사전 계산하는 트랙.
생성형 AI를 후보 검색·정렬에 쓰지 않는다. 서빙 요청은 PostgreSQL의 사전 계산 결과만 조회한다.

설계 근거: `docs/Pickage_기능별_개발_구상안_0917.md` §3.3~3.5, §4.1, §4.2, §14.

> **재학습 관련 안내 (2026-09-14)**: 모델 재학습(재파인튜닝)은 최대한 지양하는 방향으로
> 결정했다. 이 문서에서는 재학습 파이프라인 구축·운영에 관한 서술을 뺐다 — 서빙 모델의
> 스펙과 학습 이력은 `ai/MODEL_CONTRACT.md`에 남아 있다. 아래 내용은
> **이미 만들어진 모델을 유지·서빙하는 배치**(`similarity/`)에 집중한다.
>
> **정정 (2026-09-18)**: 실제 `@production`은 아래 설명하는 v7이 아니라 `v7-v5clean`이다
> (2026-09-17 첫 실운영 배치에서 확인, S15P21A506-387). 스펙·학습 조건·recall은
> `ai/MODEL_CONTRACT.md`의 "모델 — v7-v5clean" 절 참고.

## 폴더

| 폴더 | 역할 | 실행 위치 |
|---|---|---|
| `similarity/` | 유사도 배치 파이프라인 컨테이너 (§4.1 6단계). CPU 추론·재랭킹·채점 게이트·MinIO 산출 | EC2 #1 (x86_64 — 2026-09-09 확인, 문서는 t4g/ARM 전제), cron 1회성 |
| `training/` | 과거 학습 실행 스크립트의 참조용 사본. 재학습 파이프라인 자동화는 진행하지 않는다 | jupyter05 (GPU) |

## 전체 흐름 (방식 C — SIM/LOAD 분리)

```
[MLflow @production 모델]
        │
        ├── ai/similarity 배치: 변경분 재임베딩 → 의미 검색 top-30 → 구조적 관문 →
        │   cos 정렬(§4.2) → 채점 게이트(Recall@N/@10) → MinIO 산출물 + manifest
        ▼
[별도 로더]  manifest 읽어 similar_packages staging → RENAME + model_production 포인터 전환
        ▼
[EC2 #2]  Spring Boot 는 PostgreSQL 결과만 조회
```

`ai/similarity` 이미지는 PostgreSQL을 건드리지 않는다 (`psql`·PG 드라이버 없음).

## 현재 상태 (2026-09-14)

**완료**
- CPU 추론 처리량 (더미벡터): EC2 #1에서 10만×384dim flat cosine top-20 = 110.9초 — S15P21A506-169 (티켓엔 "t4g/ARM"으로 기재됐으나 실측 노드는 x86_64)
- **ONNX export 완료 (2026-09-09)**: GPU에서 PyTorch vs ONNX 오차 0.000000. pooling(CLS)+L2 정규화는 ONNX **밖**. — S15P21A506-287
- 유사도 배치 컨테이너 골격 (`ai/similarity/`) — S15P21A506-282
- 배치 본체 구현 + 2단계 랭커(검색 top-30 → 구조적 관문 → cos 정렬) — MR !102, S15P21A506-168, 2026-09-11 develop 머지
- **v7 모델로 교체 (2026-09-11)** — S15P21A506-329. ONNX export·MinIO 업로드까지 완료, 상세 배경·스펙은
  `ai/MODEL_CONTRACT.md` 참고. **EC2 #1 CPU 실측 검증(S15P21A506-287)은 v7으로 아직 안 함 — 미해결.**
- **인지도 관문 추가 (2026-09-22)** — S15P21A506-450. `--downloads-floor`(기본 500,000) 구현 +
  단위테스트, 위 "재랭킹 규칙" 절 참고. EC2 #1 실배치 반영은 다음 배포에서.

**진행 중 / 블로커**

| # | 블로커 | 담당 |
|---|---|---|
| B1 | EC2 #1 = 4 vCPU / 15 GiB / **swap 2 GiB (컨테이너에는 0)** (Intel Xeon 8259CL, x86_64). Spark(~10G)·MinIO·MLflow·cron ETL과 공유 → 동시 실행 시 OOM 위험은 그대로다. AI 배치를 Spark ETL과 시간 겹치지 않게 cron 스케줄 분리 필요 (미정). **AI 배치를 compose 에 올릴 때 `mem_limit` 과 `memswap_limit` 을 짝으로 쓸 것** — 한쪽만 쓰면 상한이 조용히 2배가 된다 (deploy/prod/README.md 의 "Swap") | AI + 인프라 |

## 앞으로의 단계

| Step | 내용 | 티켓 |
|---|---|---|
| 1 | **ONNX export + EC2 #1 CPU(x86_64) 추론 검증** — export는 완료(2026-09-09), 남은 건 EC2에서 수치 일치·held-out recall 동등·처리량 실측 | S15P21A506-287 |
| 2 | `ai/MODEL_CONTRACT.md` v7 갱신 — **완료**, 단 EC2 CPU 실측·저장 경로 불일치는 미해결 | S15P21A506-329 |
| 2b | `ai/MODEL_CONTRACT.md`에 실제 운영 모델(v7-v5clean) 스펙·recall·저장 경로 반영 — **완료** (2026-09-18) | S15P21A506-387 |
| 3 | 대규모 recall 재검증 (10만 색인 + 234 held-out, "deprecated 51K" 정체 확인). 51K holdout 정답 노후화 문제 있음 — 아래 "채점 게이트 설계 메모" 참고 | S15P21A506-169 |
| 4 | 배치 본체 구현 (`similarity_batch_pipeline.py` 스텁 채우기) — **완료**, 2026-09-11 develop 머지 | MR !102, S15P21A506-168 |
| 5 | `similar_packages` 로더 (방식 C의 LOAD). `pipeline/postgresql/load.py` 패턴 재사용 | 신규 |
| — | 제외 규칙·오추천 필터·재현성 검증 | S15P21A506-172, 173, 174 |

**손대지 말 것 (지금)**: 재학습(재파인튜닝) 파이프라인 자체(자동 트리거 포함, 236) — 재학습은 최대한
지양하는 방향으로 결정(2026-09-14), 리랭킹(S15P21A506-170, 보류), 근거 카드·RAG(147, 175~180 — 확장).

## 재랭킹 규칙 (§4.2)

2단계 랭커 (`제안_유사후보_v1랭커_2단계분리_260910.md`, **2026-09-10 팀 승인**). `DEC-RANK-20260909-01` 의
deprecated 완전 제외·`move_lift` 배제는 그대로 유지하고, top-K 50→20 조항을 검색/노출 분리로 대체한다.

1. **의미 검색** — cos 유사도로 `--retrieve-k`(기본 **30**) 개를 뽑는다. 최종 노출(3)보다 넉넉히.
2. **구조적 관문** (`--gate`, 기본 **on**) — 점수 조정이 아니라 통과/탈락:
   - plugin/adapter/preset/loader·비말단 config (이름·keywords) → drop
   - same-family: 우산↔하위모듈(`d3`↔`d3-axis`)·같은 포장(`lodash`↔`lodash-es`)·같은 `@scope` → drop
   - 보완재 drop (`--dependents`, 선택) — dependents 겹침 `교집합 ÷ min(두 dependents 수) > 0.3` (**구현 완료, 2026-09-16, `S15P21A506-173`**). `--dependents` 를 안 주면 `--package-text` 와 같은 폴더의 `package_dependents.parquet` 를 찾아 쓰고, 그것도 없으면 **경고 로그를 남기고 이 관문만 건너뛴다**(배치는 계속 돈다). manifest 의 `params.gate_drops.complement` 는 관문이 안 돌았으면 `null`, 돌았으면 걸러낸 쌍 수이고, `params.dependents_coverage` 는 이번 패키지 중 dependents 행이 있는 비율(`pool`·`with_dependents`·`ratio`)이다 — 후보 풀이 dependents 파일보다 커지면 이 비율이 내려간다
3. **인지도 관문** (`--downloads-floor`, 기본 **500,000**, S15P21A506-450) — `downloads_last_month`가
   이 값 미만인 후보는 drop. 정보가 없는 후보(None)도 통과 안 시킴(보수적).
4. **정렬** — 관문 통과분을 **cos 유사도 순 단독**. 다른 가·감점 없음.
5. 노출 최대 3 → 상위 2개 기본 선택. 내부 score·계수는 API에 노출하지 않는다.

- **(정정, 2026-09-22, S15P21A506-450) 인지도(downloads)를 관문으로 쓴다.** 이전엔 "인기도·
  다운로드·채택도를 순위 신호로 쓰지 않는다"(제안 §3.3 원문)가 방침이었으나, 정답 기준 자체가
  "기능 유사"에서 "기능 유사 + 인지도"로 기획 개정됨에 따라 뒤집혔다. `--downloads-floor`는
  cos처럼 상대 정렬 신호가 아니라 구조적 관문과 같은 **pass/fail 하드컷**이다 — cos 자체엔
  여전히 절대 임계값을 안 쓴다(`DEC-RANK-20260910-01`, 도메인마다 스케일이 달라 불안정).
  실측(`ai/training/eval_gate_ranking.py`, "정답(B)도 인지도가 있어야 진짜 정답"으로 골드셋을
  다시 채점): 하한 미적용 대비 recall@3 이 0.130→**0.332**(50만 하한)로 개선 — 순수 cos
  정렬이 더 비슷하게 생긴 무명 패키지에 밀려 "인기 있는 진짜 대안"조차 놓치고 있었음을 확인.
  50만보다 낮은 하한(1만/5만/10만)도 다 개선이었지만 50만이 가장 좋았다.
- deprecated 지목 가산 없음 (`DEC-RANK-20260909-01`).
- `--no-gate` 로 관문을 끄면 검색 30개를 그대로 cos 순 정렬 (인지도 관문은 `--downloads-floor 0`
  으로 별도로 꺼야 함 — `--gate` 와 독립적).

**`is_same_family` 보완 이력 (S15P21A506-334)**: 스코프 없는 이름이 상대방의 스코프(조직명) 자체와
정확히 같은 경우(`parcel`↔`@parcel/graph`)와, `@types/x`↔`x`(DefinitelyTyped 타입 선언) 두 규칙을
추가했다 — 둘 다 922K 풀 recall 재검증 중 실제로 자기 서브패키지가 "대안"으로 뜬 사례를 보고 반영함.

**앞으로 지켜볼 것(아직 미반영)**: `babel-core`→`@babel/core`처럼 **스코프 없던 이름이 그대로 스코프로
옮겨간 리네이밍**(이름 전체가 아니라 접두어만 일치) 패턴도 이론상 같은 계열로 잡아야 하지만, 이건 판정을
느슨하게 만들어 오탐 위험이 커진다(예: `eslint-plugin-react`가 `@eslint/js`와 잘못 묶일 수 있음). 아직
우리 실패 사례(33개)에서 실제로 발견된 적은 없어 지금은 구현하지 않는다 — 실제 사례가 나오면 그때
`is_same_family`에 추가할 것.

## 채점 게이트 설계 메모 (§4.1, S15P21A506-335)

`scoring_gate()`는 **재학습(재파인튜닝) 트리거가 아니다.** "직전 운영값 대비 recall 하락 시 중단"의
"중단"은 `gate_allows_success()`를 통해 `_SUCCESS`를 안 남겨서 **이번 배치 결과의 발행만 막는 것**이다.
자동 재학습 트리거는 위 "손대지 말 것" 목록에 있는 별개의(아직 범위 밖인) 기능이다.

**51K holdout 정답 노후화(staleness) 문제 (2026-09-14 발견)**: 정답이 "A → B"로 고정돼 있는데 B 자신이
나중에 리브랜딩해 C가 되면, 모델이 C라고 정확히 답해도 낡은 정답 기준으로는 오답 처리된다. 실제 위험도
확인됨 — `functional_succession`/`succession_mid` 학습 데이터 버킷(같은 종류의 "폐기→대체" 데이터)을
다른 LLM으로 교차검증했더니 144쌍 표본의 72.9%가 "다른 회사 제품"이 아니라 "같은 저자의 리브랜딩"이었다.

이 홀드아웃의 원천은 `pipeline/duckdb/build_deprecated_dataset.py` → `datasets/deprecated_replacement_260831/`
(28,241행, deps.dev BigQuery의 `Deprecated` 원문을 정규식으로 파싱). 이미 있는 것: A의 폐기 문구 원문,
대체품(B) 이름, A의 GitHub 저장소(`source_repo`), **대체품 생존 여부(`replacement_alive` — 2,325건이
이미 "대체품도 죽음"으로 표시돼 있어 staleness 검증에 바로 재사용 가능)**. 없는 것: B의 GitHub 저장소
정보라 "A와 B가 같은 팀인지" 비교가 불가능 — 데이터 팀에 보완 요청함(S15P21A506-338).

**정밀도 함정**: 이 데이터셋의 `replacement_confidence`(high/medium)는 "정규식이 이름을 제대로
추출했는지"의 신뢰도일 뿐, "같은 팀인지"와는 무관하다. 이름 때문에 오해하기 쉽고, 실제로 이 혼동이
위 72.9% 오류율 사고의 원인 중 하나로 보인다.

## 관련 문서

- `docs/Pickage_기능별_개발_구상안_0917.md` — 시스템 확정안 (이전 세대는 `docs/history/` 로 이관)
- `datasets/deprecated_replacement_260831/`, `datasets/migration_pairs_260908/`, `datasets/feature_candidates_260908/` — 학습 데이터
- `pipeline/collectors/keywords/` — `package_text` (임베딩 입력) 수집
- `pipeline/postgresql/` — 적재기 패턴 (방식 C 로더 참조)
