# ai — Pickage 유사 패키지 후보 모델

기준 패키지의 `description + keywords` 임베딩으로 **유사/대체 후보 최대 3개**를 사전 계산하는 트랙.
생성형 AI를 후보 검색·정렬에 쓰지 않는다. 서빙 요청은 PostgreSQL의 사전 계산 결과만 조회한다.

설계 근거: `docs/Pickage_기능별_개발_구상안_0909.md` §3.3~3.5, §4.1, §4.2, §14.

## 폴더

| 폴더 | 역할 | 실행 위치 |
|---|---|---|
| `similarity/` | 유사도 배치 파이프라인 컨테이너 (§4.1 6단계). CPU 추론·재랭킹·채점 게이트·MinIO 산출 | EC2 #1 (x86_64 — 2026-09-09 확인, 문서는 t4g/ARM 전제), cron 1회성 |
| `training/` | GPU 재학습 오케스트레이터(`run_pipeline.sh`)의 **참조용 사본**. 학습 코드 본체(`finetune_bge_small_lora.py`, `merge_and_export_onnx_v6.py` 등)는 jupyter05에만 있고 레포에 커밋하지 않는다 | jupyter05 (GPU) |

> 학습 코드가 레포 밖이므로 **재현성은 산출물 계약으로만 보장**된다. 학습 실행마다
> `run_manifest.json`(코드 git hash·데이터 스냅샷 ID·하이퍼파라미터·base 모델 SHA)을
> 모델 산출물과 함께 남긴다.

## 전체 흐름 (방식 C — SIM/LOAD 분리)

```
[jupyter05 GPU]  training_pairs pull → LoRA 파인튜닝 → merge → ONNX export
        │                                                        │
        │  (EC2 #1 SSH 터널: Tailscale 대체, §3.4 이탈 — 인프라 승인 필요)
        ▼                                                        ▼
[EC2 #1 CPU]  MLflow @candidate 등록·평가·@production 승격         │
        │                                                        │
        ├── ai/similarity 배치: 변경분 재임베딩 → 의미 검색 top-30 → 구조적 관문 →
        │   cos 정렬(§4.2) → 채점 게이트(Recall@N/@10) → MinIO 산출물 + manifest
        ▼
[별도 로더]  manifest 읽어 similar_packages staging → RENAME + model_production 포인터 전환
        ▼
[EC2 #2]  Spring Boot 는 PostgreSQL 결과만 조회
```

`ai/similarity` 이미지는 PostgreSQL을 건드리지 않는다 (`psql`·PG 드라이버 없음).

## 현재 상태 (2026-09-09)

**완료**
- GPU 서버 세팅 (jupyter05, L40S ×4) — S15P21A506-232
- 임베딩 모델 선정: **bge-small-en-v1.5 + LoRA** (r=16, lr=5e-5, batch=32, epoch=10) — S15P21A506-167, 237
- 실제 LoRA 파인튜닝·대규모 재검증 (2026-09-08) — S15P21A506-237
  - 계승형 recall@3 0.864 vs 베이스라인 0.802 (z=5.57, 유의)
  - 공존형 recall@3 0.833 vs 0.806 (미유의 — 평가셋 설계 한계)
  - 산출물: `train_combined_v6.jsonl`(20,132쌍), `held_out_eval_bundle_v5.json`, `lora_final_v6`
- CPU 추론 처리량 (더미벡터): EC2 #1에서 10만×384dim flat cosine top-20 = 110.9초 — S15P21A506-169 (티켓엔 "t4g/ARM"으로 기재됐으나 실측 노드는 x86_64)
- **ONNX export 완료 (2026-09-09)**: `lora_final_v6` merge → `onnx_bge_v6/model.onnx` (opset 18, legacy TorchScript exporter, `dynamo=False`). GPU에서 PyTorch vs ONNX 오차 0.000000. pooling(CLS)+L2 정규화는 ONNX **밖**. — S15P21A506-287
- 유사도 배치 컨테이너 골격 (`ai/similarity/`) — S15P21A506-282
- 배치 본체 구현 + 2단계 랭커(검색 top-30 → 구조적 관문 → cos 정렬) — MR !102, S15P21A506-168, 2026-09-11 develop 머지
- **v7 모델로 교체 (2026-09-11)** — S15P21A506-329. v6는 학습셋 positive 86%가 리네임이라 near-duplicate만 학습된 것으로 판명(재파인튜닝 금지). v7은 새 학습셋(`ai/training/train_v7_hiconf_norebrand.jsonl`)으로 재학습, held-out "기능적 대안" recall@3 **0.153**(base 대비 +40%). ONNX export·MinIO 업로드까지 완료, 상세 스펙은 `ai/MODEL_CONTRACT.md` 참고. **v6가 했던 EC2 #1 CPU 실측 검증(S15P21A506-287)은 v7으로 아직 안 함 — 미해결.**

**진행 중 / 블로커**

| # | 블로커 | 담당 |
|---|---|---|
| B1 | `run_pipeline.sh`의 `EC2_HOST` 실제값 = EC2 #1(MinIO·MLflow 노드) 확인 | 인프라 |
| B2 | jupyter05 → EC2 #1 pem 키 배치 + 보안그룹 22번에 jupyter05 IP 허용 | 인프라 |
| B3 | Tailscale→SSH 터널 대체안 승인 (§3.7 내부 포트 접근 규칙 변경) | 인프라 + AI |
| B4 | MinIO **읽기전용** curated 키 (admin 아님 — §3.7). 공유 서버라 중요 | 인프라 |
| B5 | `pickage-curated`에 `training_pairs` 존재 여부 — S7 Spark 잡 미구현 → v6 학습셋이 GPU 로컬에만 있을 가능성 | AI |
| B6 | EC2 #1 MLflow(5000) 배포 — 미배포. `run_pipeline.sh` 5단계·S15P21A506-236 공통 블로커 | 인프라 |
| B7 | EC2 #1 = 4 vCPU / 15 GiB / **swap 2 GiB (컨테이너에는 0)** (Intel Xeon 8259CL, x86_64). Spark(~10G)·MinIO·MLflow·cron ETL과 공유 → 동시 실행 시 OOM 위험은 그대로다. AI 배치를 Spark ETL과 시간 겹치지 않게 cron 스케줄 분리 필요 (미정). **AI 배치를 compose 에 올릴 때 `mem_limit` 과 `memswap_limit` 을 짝으로 쓸 것** — 한쪽만 쓰면 상한이 조용히 2배가 된다 (deploy/prod/README.md 의 "Swap") | AI + 인프라 |

## 앞으로의 단계

| Step | 내용 | 티켓 |
|---|---|---|
| 0 | `./run_pipeline.sh --no-train` — 터널 + MinIO pull 검증. B1·B2·B4·B5 확인 | — |
| 1 | B5 판정: `training_pairs` 없으면 v6 학습셋을 MinIO `pickage-curated`에 업로드 (S7 임시 대체) | 신규 (조건부) |
| 2 | `run_pipeline.sh` TODO 채우기 — 3개 스크립트 `--help` 확인, `TRAIN_CMD` 하이퍼파라미터, `prepare_training_format()`, `run_manifest.json` | 신규 |
| 3 | 학습 + ONNX export (MLflow 제외). 산출물 수동 저장 | Step 2 티켓 |
| 4 | **ONNX export + EC2 #1 CPU(x86_64) 추론 검증** — export는 완료(2026-09-09), 남은 건 EC2에서 수치 일치·held-out recall 동등·처리량 실측 | S15P21A506-287 |
| 5 | `ai/MODEL_CONTRACT.md` v7 갱신 — **완료**, 단 EC2 CPU 실측·저장 경로 불일치는 미해결 | S15P21A506-329 |
| 6 | 대규모 recall 재검증 (10만 색인 + 234 held-out, "deprecated 51K" 정체 확인) | S15P21A506-169 |
| 7 | 인프라: MLflow 배포(B6) → `register_mlflow` 활성화 → @candidate/@production 경로 | S15P21A506-236 |
| 8 | 배치 본체 구현 (`similarity_batch_pipeline.py` 스텁 채우기) — **완료**, 2026-09-11 develop 머지 | MR !102, S15P21A506-168 |
| 9 | `similar_packages` 로더 (방식 C의 LOAD). `pipeline/postgresql/load.py` 패턴 재사용 | 신규 |
| — | 제외 규칙·오추천 필터·재현성 검증 | S15P21A506-172, 173, 174 |

**손대지 말 것 (지금)**: 리랭킹(S15P21A506-170, 보류), 근거 카드·RAG(147, 175~180 — 확장), 재파인튜닝 자동 트리거(236의 자동화 부분).

## 재랭킹 규칙 (§4.2)

2단계 랭커 (`제안_유사후보_v1랭커_2단계분리_260910.md`, **2026-09-10 팀 승인**). `DEC-RANK-20260909-01` 의
deprecated 완전 제외·`move_lift` 배제는 그대로 유지하고, top-K 50→20 조항을 검색/노출 분리로 대체한다.

1. **의미 검색** — cos 유사도로 `--retrieve-k`(기본 **30**) 개를 뽑는다. 최종 노출(3)보다 넉넉히.
2. **구조적 관문** (`--gate`, 기본 **on**) — 점수 조정이 아니라 통과/탈락:
   - plugin/adapter/preset/loader·비말단 config (이름·keywords) → drop
   - same-family: 우산↔하위모듈(`d3`↔`d3-axis`)·같은 포장(`lodash`↔`lodash-es`)·같은 `@scope` → drop
   - 보완재 감점(dependents 교집합 `> 0.3`) → **의존 그래프(Spark) 준비 후 추가** (`S15P21A506-173`)
3. **정렬** — 관문 통과분을 **cos 유사도 순 단독**. 다른 가·감점 없음.
4. 노출 최대 3 → 상위 2개 기본 선택. 내부 score·계수는 API에 노출하지 않는다.

- **인기도·다운로드·채택도를 순위 신호로 쓰지 않는다** (제안 §3.3). 생존·실체는 1단계 자격 필터의 관문일 뿐.
- deprecated 지목 가산 없음 (`DEC-RANK-20260909-01`).
- `--no-gate` 로 관문을 끄면 검색 30개를 그대로 cos 순 정렬.

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

- `docs/Pickage_기능별_개발_구상안_0909.md` — 시스템 확정안 (0904 는 `docs/history/` 로 이관)
- `datasets/deprecated_replacement_260831/`, `datasets/migration_pairs_260908/`, `datasets/feature_candidates_260908/` — 학습 데이터
- `pipeline/collectors/keywords/` — `package_text` (임베딩 입력) 수집
- `pipeline/postgresql/` — 적재기 패턴 (방식 C 로더 참조)
