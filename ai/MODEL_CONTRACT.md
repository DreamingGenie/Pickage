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
> (MLflow `pickage-similarity` 버전 2, 2026-09-15 등록). 이 문서의 "모델"·"검증 기록" 절은
> 아직 v7만 설명한다 — v7-v5clean 스펙은 바로 아래 "## 모델 — v7-v5clean (현재 운영)" 절을 볼 것
> (S15P21A506-387).

## 모델 — v7-v5clean (현재 운영, 계약 미완성)

**2026-09-17 첫 실운영 배치에서 확인됨.** 아래 v7(§"모델") 대신 **이 모델이 실제로 서빙 중**인데,
학습 조건·성적이 이 문서에 없었다. MLflow가 경로를 알려주므로 배치 실행 자체는 문제없이
됐지만, 후보 품질을 판단할 근거도 다음 모델과 비교할 기준도 지금은 없다.

| | 값 |
|---|---|
| MLflow 등록 | `pickage-similarity` 버전 2, 2026-09-15 03:52 등록, 별칭 `@production` |
| MLflow source | `s3://pickage-mlflow-artifacts/v7-v5clean` |
| model_version 문자열 | `bge-small-v7-v5clean-batch32-step500` |
| base | `BAAI/bge-small-en-v1.5` — v7과 동일 추정 (**미확인, 아래 TODO**) |
| 어댑터 | LoRA, **batch32 / step500** (v7은 batch32/10epoch/**step1310** — 왜 1310이 아니라 500에서 멈췄는지 **미확인**) |
| 학습 데이터 | `v5clean` — **무엇을 정제(clean)했는지, v7 학습셋과 관계가 무엇인지 미확인** |
| 학습 스크립트 | **미확인** — `ai/training/finetune_bge_small_lora_v7.py`를 옵션만 바꿔 썼는지, 별도 스크립트였는지. 레포에 없다면 **왜 커밋 안 됐는지도 같이 남길 것**(커밋 안 된 실험은 재현 불가) |
| 병합 방식 | **미확인** — v7과 같은 `BaseTunerLayer.merge()`인지 |

**TODO (S15P21A506-387 — 담당 오세진)**: 위 굵게 표시한 항목은 MLflow run의 params/tags를
먼저 확인하고(아래 명령), 없으면 jupyter05 학습 로그에서 가져온다.

```bash
curl -fsS "http://127.0.0.1:5000/api/2.0/mlflow/registered-models/get-version?name=pickage-similarity&version=2" \
  | tr ',' '\n' | grep -E '"key"|"value"|source|run_id'
# run_id 를 알아내면:
# mlflow.get_run(<run_id>) 로 params(하이퍼파라미터)·metrics(recall 등)·tags 를 한 번에 확인
```

### 실행 환경·처리량 — EC2 #1 실측 (2026-09-17, 첫 실운영 배치)

v7 절의 "실행 환경"과 하드웨어는 동일(EC2 #1, 4 vCPU/15 GiB, x86_64). v7-v5clean 기준 실측값은
아래가 처음이다 — v7 자체는 이 실측이 아직 없다(위 "상태" 참고).

| 검증 | 결과 |
|---|---|
| 코퍼스 → 임베딩 → top-30 검색 → 구조적 관문까지 | **1,884.8초** (29,164개 임베딩) |
| 메모리 최고점 | **5.236 GiB** (55초간 소수점 셋째 자리까지 고정 — 추론 엔진이 작업 공간을 한 번 크게 잡고 재사용) |
| 컨테이너 `mem_limit` | 2 GiB로는 OOM, 4 GiB도 임베딩 시작 15초 뒤 OOM, **8 GiB에서 완주** (S15P21A506-384에서 상한 조정 진행 중) |
| held-out recall@3 / @10 | **미확인** — v7은 recall@3 0.153 / recall@10 0.306(기능적 대안 183쌍/47,530 코퍼스). 같은 held-out 셋으로 이 모델 수치를 채울 것 (TODO) |
| 관문 통과 통계 | 검색 874,920쌍 → plugin_adapter 81,867 · same_family 180,273 · repo_archived 3,807 제거 → **608,973쌍** |

### 저장 위치 — 실제 경로 (v7의 "계약 경로"와 다름)

v7과 같은 문제다: 계약 문서가 말하는 경로(`pickage-mlflow-artifacts/models/similar-packages/vN/`)와
**실제 업로드 경로가 다르다.**

- **실제 경로**: `pickage-mlflow-artifacts/v7-v5clean/` (평평한 구조, MinIO 웹 콘솔로 수동 업로드)
- 배치 실행 기록: `pickage-vectors/model=v2/corpus=package-text-20260908-v1/run_manifest.json`
- 배치/로더가 계약 경로(`models/similar-packages/v2/`)를 기대한다면 못 찾는다 — v7과 **같은 미해결
  사안**이라 v7 절의 "저장 위치·보관 정책"에서 한 번에 정리하거나, 두 모델 다 계약 경로로
  재배치할지 결정이 필요하다.

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
- **모델(v7 실제 업로드, 계약과 경로 다름 — 미해결)**: `pickage-mlflow-artifacts/onnx_bge_v7/`(평평한 구조, 위 계약 경로가 아님) — MinIO 웹 콘솔로 수동 업로드하며 컨벤션을 안 맞춘 것. `model.onnx` + tokenizer 2종 + `run_manifest.json` + `_SUCCESS`, 5개 파일. **배치/로더가 계약 경로(`models/similar-packages/v7/`)를 기대한다면 못 찾는다 — 재배치하거나 계약을 이 경로로 갱신할지 정해야 함.**
- 벡터: MinIO `pickage-vectors/vN/` — 10만 임베딩, 버전당 ~146 MiB.
- 학습 데이터: MinIO `pickage-curated/` — `train_combined_vN.jsonl`, `held_out_eval_bundle_vN.json`.
- MLflow 미배포(S15P21A506-236)라 당분간 수동 업로드.

**보관 정책**: `@production` + 직전 2개 버전만 유지 (그 이전은 삭제). AI 트랙 MinIO 용량 목표 **~2 GB, 상한 4 GB**. 디스크(320 GB)·계획 EBS(200 GB) 대비 무시 가능.
