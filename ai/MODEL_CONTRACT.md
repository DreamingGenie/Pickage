# 임베딩 모델 산출물 계약 (v7)

`ai/similarity` 배치(EC2 #1)가 소비하는 ONNX 모델의 규격. 학습 코드는 GPU 서버(jupyter05)에만
있으므로 **이 문서가 GPU↔레포 경계의 계약**이다. 값이 바뀌면 이 문서를 먼저 고친다.

상태: **검증 진행 중** (S15P21A506-329). GPU 박스에서 PyTorch vs ONNX 수치 일치·MinIO 업로드는
확인됨. **v6(S15P21A506-287)와 달리 EC2 #1 CPU 실측(수치 일치·처리량·held-out recall 동등성)은
아직 안 함** — 배치가 v7을 실제로 쓰기 전에 필요.

v6 대비 학습 데이터·평가 방식이 바뀌었다 (v6의 "계승형/공존형" recall과 v7의 "기능적 대안" recall은
직접 비교 불가 — 평가셋·태스크 정의가 다름). v6 재파인튜닝은 금지 — v6 학습셋 positive 86%가
리네임이라 near-duplicate 만 학습된 것으로 판명됨.

> ⚠️ **지금 실제로 `@production`이 가리키는 모델은 아래 v7이 아니라 `v7-v5clean`이다**
> (MLflow `pickage-similarity` 버전 2, 2026-09-15 등록). 아래 v7 관련 절(모델·ONNX·Export·
> 추론 인터페이스·후처리·실행 환경)은 base 모델·ONNX 규격·추론 방식이 공통이라 v7-v5clean에도
> 그대로 적용된다. **학습 조건·recall 성적만 갈리므로** v7-v5clean 전용 정보는 바로 아래
> "## 모델 — v7-v5clean (현재 운영)" 절에 모아뒀다 (S15P21A506-387, 2026-09-18 조사 완료).

## 모델 — v7-v5clean (현재 운영)

**2026-09-17 첫 실운영 배치에서 이 모델이 실제로 서빙 중인 것이 확인됐다.** 학습 조건·성적이
이 문서에 없었던 문제는 2026-09-18 jupyter05·MinIO 직접 조사로 해소했다(아래).

| | 값 |
|---|---|
| MLflow 등록 | `pickage-similarity` 버전 2, 2026-09-15 03:52 등록, 별칭 `@production` |
| MLflow source | `s3://pickage-mlflow-artifacts/v7-v5clean` |
| model_version 문자열 | `bge-small-v7-v5clean-batch32-step500` |
| base | `BAAI/bge-small-en-v1.5` — v7과 동일 (jupyter05 `v7-v5clean/run_manifest.json` 확인) |
| 어댑터 | LoRA r=16, alpha=32, dropout=0.05, target_modules=all-linear — v7과 동일. `batch32 / step500` (v7은 batch32/10epoch/**step1310**) |
| **step500인 이유** | 끝까지(1310) 학습한 v7과 달리, `sweep_checkpoints.py`로 여러 체크포인트를 스윕해 `test_alternatives_full_v2.jsonl`(315쌍) recall@3 기준으로 **중간 체크포인트를 직접 선택**했다. step1310까지 학습은 했으나 500이 검증 recall이 가장 좋아 그 시점 가중치를 채택 |
| 학습 데이터 | `train_v7_hiconf_v5.jsonl`, **4,699쌍**. lineage: v2(4,456) → v3(4,278, migration 필터 +337) → **v5(4,699, hard-negative 마이닝 flip +84)** — v7 학습셋(`train_v7_hiconf.jsonl`, 5,684쌍 중 positive 4,162)과는 별개 계열이며, v5clean은 그 이후 세대(v2clean→v3clean→v5clean)의 최종 정제판 |
| 하이퍼파라미터 | epochs 10, batch_size 32, learning_rate 5e-5, warmup_ratio 0.1, loss `MultipleNegativesRankingLoss` — v7과 동일 |
| 학습 스크립트 | `ai/training/finetune_bge_small_lora_v7.py` — v7과 같은 스크립트, `run_name="v5clean"`으로 재실행(옵션만 다름). 레포에 커밋돼 있어 재현 가능 |
| 병합 방식 | v7과 같은 레이어 단위 병합(`BaseTunerLayer.merge()`, `get_peft_model` 미사용) |

**출처**: `pickage-mlflow-artifacts/v7-v5clean/run_manifest.json` (jupyter05에서 학습 시 같이 기록됨 — MinIO에 이미 있었는데 이 문서에 반영이 안 돼 있었다). MLflow run params/metrics 별도 조회는 불필요했다.

### 실행 환경·처리량 — EC2 #1 실측 (2026-09-17, 첫 실운영 배치)

v7 절의 "실행 환경"과 하드웨어는 동일(EC2 #1, 4 vCPU/15 GiB, x86_64). v7-v5clean 기준 실측값은
아래가 처음이다 — v7 자체는 이 실측이 아직 없다(위 "상태" 참고).

| 검증 | 결과 |
|---|---|
| 코퍼스 → 임베딩 → top-30 검색 → 구조적 관문까지 | **1,884.8초** (29,164개 임베딩) |
| 메모리 최고점 | **5.236 GiB** (55초간 소수점 셋째 자리까지 고정 — 추론 엔진이 작업 공간을 한 번 크게 잡고 재사용) |
| 컨테이너 `mem_limit` | 2 GiB로는 OOM, 4 GiB도 임베딩 시작 15초 뒤 OOM, **8 GiB에서 완주** → compose 상한을 8 GiB로 조정(S15P21A506-384, 2026-09-25) |
| 관문 통과 통계 | 검색 874,920쌍 → plugin_adapter 81,867 · same_family 180,273 · repo_archived 3,807 제거 → **608,973쌍** |

### held-out recall — 2026-09-18 jupyter05 GPU에서 직접 재측정

`eval_recall.py --model ./merged_bge_v7_v5clean_best --pool candidate_pool_full_922k.jsonl --test test_alternatives_full_v2.jsonl --apply-gates --dependents candidate_pool_package_dependents.parquet`

| 검증 | 결과 |
|---|---|
| 코퍼스 | 29,376개 (원본 29,310 + 평가쌍 누락분 보충 66) — **운영 배치 실제 코퍼스(29,164개)와 거의 동일 크기** |
| 평가쌍 | 315개, 17개 도메인 (`test_alternatives_full_v2.jsonl`) |
| recall@3 | **0.238** |
| recall@10 | **0.511** |
| recall@30 | **0.740** |
| 관문 | ON (plugin/adapter · same-family · dependents 보완재, `similarity_batch_pipeline.py`와 동일 로직) |

**v7의 recall@3 0.153 / recall@10 0.306과 직접 비교하지 말 것.** 조건이 셋 다 다르다 —
① eval셋 크기(183쌍 vs 315쌍, 315쌍은 183쌍에서 확장된 상위집합), ② 코퍼스 크기(47,530 vs
29,376), ③ 관문 적용 여부(v7 쪽 `run_manifest.json`에 gate 기록이 없어 순수 코사인 recall로
추정됨, v5clean은 gate=ON). 다음 모델과 비교할 때는 **반드시 이 문서의 조건(코퍼스
`candidate_pool_full_922k.jsonl`, gate=ON, eval셋 `test_alternatives_full_v2.jsonl`)을
그대로 맞춰서 재측정할 것.**

이전에도 같은 모델·eval셋으로 3차례 더 평가한 기록이 jupyter05에 있는데(코퍼스 크기·게이트
버그 수정 시점이 각기 달라 recall@3 0.225~0.257 사이로 갈렸다), 위 표는 그중 **가장 최신
게이트 코드(S15P21A506-334 반영)로, 가장 운영과 가까운 코퍼스 크기로 다시 돌린 값**이라 이
문서의 대표값으로 삼는다.

### 저장 위치

실제 경로는 `pickage-mlflow-artifacts/v7-v5clean/` — v7과 같은 "계약 경로와 실제 경로가 다르다"
문제라 v7 것과 합쳐서 "## 저장 위치·보관 정책" 절에 정리했다. 배치 실행(적재) 기록은
`pickage-vectors/model=v2/corpus=package-text-20260908-v1/run_manifest.json`.

## 모델

| | 값 |
|---|---|
| base | `BAAI/bge-small-en-v1.5` (BERT, WordPiece, 384-dim, CLS pooling) |
| 어댑터 | LoRA `lora_final_v7_full10ep` (jupyter05 `~/lora_final_v7_full10ep/`) — r=16, alpha=32, dropout=0.05, target_modules=all-linear, batch32/10epoch/step1310 |
| 병합 | 레이어 단위 `BaseTunerLayer.merge()` (get_peft_model 미사용 — forward 미전파 버그 회피, v6와 동일) |
| 산출 | `~/merged_bge_v7_final/` (PyTorch), `~/onnx_bge_v7/` (ONNX) |
| 학습 스크립트 | `ai/training/finetune_bge_small_lora_v7.py` (레포에 있음, 실행은 jupyter05) |
| 학습 상세 | S15P21A506-329 (recall@3 **0.153** / recall@10 **0.306**, base 대비 +40% — held-out 도메인-분리 "기능적 대안" 183쌍, 코퍼스 47,530개 중 top-k) |

## ONNX 파일 (배포 단위)

```
model.onnx        (~138 MB)  그래프+가중치 단일 파일 — v6와 달리 external data(.data) 분리 없음
tokenizer.json                fast tokenizer (self-contained, vocab.txt 불필요)
tokenizer_config.json
```

**v6은 `model.onnx` + `model.onnx.data` 두 파일이 짝이었지만, v7은 크기가 작아 단일 `model.onnx`
파일 하나로 끝난다.** 배치 코드가 v6 기준으로 두 파일을 다 찾게 돼 있다면 확인 필요.

## Export 방식 (재현용)

- `torch.onnx.export`, **legacy TorchScript exporter** (`dynamo=False`) — torch 2.9+는 기본이 신 exporter라 명시 필요
- `opset_version=18`
- BertModel을 **2입력·1출력 wrapper**로 감쌈: `forward(input_ids, attention_mask) -> last_hidden_state` (`use_cache` 인자 충돌·출력 dict 회피)
- `dynamic_axes`: `input_ids`/`attention_mask`/`last_hidden_state` 모두 `{0: batch_size, 1: sequence_length}`
- ⚠️ export 시 "trace may not generalize" 경고 있음 — 더미(길이 32, 1건)로 trace. 검증은 다양한 길이·배치로 할 것

## 추론 인터페이스

**입력** (onnxruntime `sess.run`):
| 이름 | dtype | shape |
|---|---|---|
| `input_ids` | `int64` | `[batch, seq_len]` |
| `attention_mask` | `int64` | `[batch, seq_len]` |

**출력**: `last_hidden_state` `float32` `[batch, seq_len, 384]`

**토크나이즈**: `AutoTokenizer.from_pretrained(<dir>)` (fast, `tokenizer.json`), `padding=True, truncation=True, max_length=512`.
`max_length=512` 확정 — `SentenceTransformer("./merged_bge_v6").max_seq_length` == 512 (학습/평가가 쓴 값, BERT position embedding 상한과 동일). 512에서 ONNX 임베딩 == ST merged 임베딩 비트 동일(pool 4197 전수). 32/128/256으로 자르면 어긋남.

**입력 텍스트 포맷** (§4.1, S15P21A506-237):
```
DESCRIPTION: {description} / KEYWORDS: {kw1, kw2, ...}
```

## 후처리 — **ONNX 밖, 배치 코드가 수행** (§4.2 전제)

ONNX는 `last_hidden_state`까지만 낸다. 배치 코드가:

```python
emb = last_hidden_state[:, 0, :]                       # 1. CLS pooling (토큰 0)
emb = emb / np.linalg.norm(emb, axis=1, keepdims=True) # 2. L2 정규화
```

의미 검색·정렬(§4.2 2단계 랭커)이 "정규화 벡터 행렬곱"을 전제하므로 2번은 필수.

## 실행 환경

- EC2 #1: Intel Xeon Platinum 8259CL @ 2.5GHz, **4 vCPU / 15 GiB RAM / swap 2 GiB**, x86_64
  (2026-09-09 확인. 0909 문서 §3.1·일부 티켓은 `t4g.xlarge` ARM 전제 — 크기는 동급, arch만 x86)
- `onnxruntime` `CPUExecutionProvider`
- 처리량 (이 스펙 실측): 10만건 재임베딩 ~20.7분 (batch 32). flat cosine top-20 별도 ~110초 (S15P21A506-169)
  2단계 랭커는 retrieve-k 30 이라 검색 비용 소폭 증가 — 재측정 필요
- ⚠️ EC2 #1은 Spark(master+worker①, ~10G)·MinIO·MLflow·cron ETL과 공유. **swap 은 호스트에만
  2 GiB 있고 컨테이너에는 `memswap_limit` 으로 0을 준다**(deploy/prod/README.md 의 "Swap") —
  동시 실행 시 OOM 위험은 그대로다 → AI 배치는 Spark ETL과 시간이 겹치지 않게 cron 스케줄 분리 필요 (미정)

## 검증 기록

### v7 (2026-09-11, S15P21A506-329) — GPU 박스까지만 검증, **EC2 #1 CPU 실측은 아직 안 함**

| 검증 | 결과 |
|---|---|
| PyTorch(merged) vs ONNX (GPU 박스) | 최대 오차 0.000000 |
| held-out recall (`merged_bge_v7_final`, **GPU**, "기능적 대안" 183쌍/47,530 코퍼스) | recall@3 **0.153** / recall@10 **0.306** |
| held-out recall (베이스라인 bge-small, GPU) | recall@3 0.109 / recall@10 0.251 |
| ONNX 임베딩: GPU 박스 CPU vs EC2 #1 CPU | **미실측** |
| 10만건 재임베딩 처리량 (EC2 #1) | **미실측** — v6는 ~20.7분(batch 32)이었으나 아키텍처 동일해도 재확인 권장 |

**미해결(배치가 v7을 쓰기 전에 필요)**: v6(S15P21A506-287)이 했던 것과 같은 EC2 #1 CPU 교차검증
(수치 일치·처리량·held-out recall 동등성)을 v7으로 아직 안 했다. 이 문서 상태를 "검증 진행 중"으로
둔 이유.

### v6 (2026-09-09, S15P21A506-287, 참고용 — v7 평가 방식과 직접 비교 불가)

| 검증 | 결과 |
|---|---|
| PyTorch(merged) vs ONNX (GPU 박스 CPU) | 최대 오차 0.000000 |
| ONNX 임베딩: GPU 박스 CPU vs EC2 #1 CPU | 완전 동일 (`sha1(round6)=9e347298a4a0`) |
| ONNX 임베딩 vs ST merged, pool 4197 전수 (max_length=512) | 최대 오차 0.00000 (비트 동일) |
| 10만건 재임베딩 처리량 (EC2 #1) | ~20.7분 (batch 32) |
| held-out recall (`merged_bge_v6`, **CPU**) | 계승형 @3 **0.865** / @20 **0.934**, 공존형 @3 0.833 / @20 0.972 |
| held-out recall (ONNX, CPU) | 계승형 @3 **0.864** / @20 **0.934** — merged-CPU와 일치 |
| held-out recall (베이스라인 bge-small, CPU) | 계승형 @3 0.802 / @20 0.912 |

**참고**: S15P21A506-237의 계승형 @20 0.945는 **GPU** 측정값. 프로덕션은 CPU라 실제 운영값은
**@20 ~0.934** (GPU/CPU 부동소수점 차이가 rank-20 경계의 ~1%를 뒤집음). 베이스라인 0.912보다
확실히 위. recall@3는 GPU/CPU 무관하게 ~0.864로 일치.

## 저장 위치·보관 정책

- 모델(계약): MinIO `pickage-mlflow-artifacts/models/similar-packages/vN/` — `model.onnx`(+ v6는 `model.onnx.data`) + tokenizer + `run_manifest.json` (+ `ref_emb.npy`). 버전당 ~265 MiB.
- **모델(v7·v7-v5clean 실제 업로드 경로, 계약과 다름 — 2026-09-18 MinIO 직접 확인)**: `pickage-mlflow-artifacts/v7/`, `pickage-mlflow-artifacts/v7-v5clean/`(둘 다 평평한 구조, 위 계약 경로가 아님) — MinIO 웹 콘솔로 수동 업로드하며 컨벤션을 안 맞춘 것. 각각 `model.onnx` + tokenizer 2종 + `run_manifest.json` + `_SUCCESS`, 5개 파일. **배치/로더가 계약 경로(`models/similar-packages/vN/`)를 기대한다면 못 찾는다 — 재배치하거나 계약을 이 경로로 갱신할지 정해야 함.** (참고: 이전 버전 문서는 v7 경로를 `onnx_bge_v7/`로 적었는데, 이는 jupyter05 **로컬** ONNX 산출 디렉터리 이름(§"모델"의 `산출` 행)과 MinIO 업로드 경로를 혼동한 것 — 실제 MinIO 경로는 `v7/`이다.)
- 벡터: MinIO `pickage-vectors/vN/` — 10만 임베딩, 버전당 ~146 MiB.
- 학습 데이터: MinIO `pickage-curated/` — `train_combined_vN.jsonl`, `held_out_eval_bundle_vN.json`.
- MLflow 미배포(S15P21A506-236)라 당분간 수동 업로드.

**보관 정책**: `@production` + 직전 2개 버전만 유지 (그 이전은 삭제). AI 트랙 MinIO 용량 목표 **~2 GB, 상한 4 GB**. 디스크(320 GB)·계획 EBS(200 GB) 대비 무시 가능.
