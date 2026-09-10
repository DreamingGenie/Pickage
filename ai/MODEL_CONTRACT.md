# 임베딩 모델 산출물 계약 (v6)

`ai/similarity` 배치(EC2 #1)가 소비하는 ONNX 모델의 규격. 학습 코드는 GPU 서버(jupyter05)에만
있으므로 **이 문서가 GPU↔레포 경계의 계약**이다. 값이 바뀌면 이 문서를 먼저 고친다.

상태: **검증 진행 중** (S15P21A506-287). x86 CPU 수치 일치·처리량은 확인됨, held-out recall
대조·MinIO 저장·tokenizer max_length 확정은 미완.

## 모델

| | 값 |
|---|---|
| base | `BAAI/bge-small-en-v1.5` (BERT, WordPiece, 384-dim, CLS pooling) |
| 어댑터 | LoRA `lora_final_v6` (jupyter05 `~/lora_final_v6/`) — 73개 레이어 |
| 병합 | 레이어 단위 `BaseTunerLayer.merge()` (get_peft_model 미사용 — forward 미전파 버그 회피) |
| 산출 | `~/merged_bge_v6/` (PyTorch), `~/onnx_bge_v6/` (ONNX) |
| 학습 상세 | S15P21A506-237 (계승형 recall@3 0.864 / @20 0.945, 공존형 0.833 / 0.972) |

## ONNX 파일 (배포 단위)

```
model.onnx        (~138 MB)  그래프
model.onnx.data   (~138 MB)  가중치 (external data) — model.onnx와 반드시 같은 디렉터리에 함께
tokenizer.json                fast tokenizer (self-contained, vocab.txt 불필요)
tokenizer_config.json
```

**`model.onnx` 와 `model.onnx.data` 는 항상 같이 이동한다.** MinIO 업로드·이미지 COPY·scp 모두.

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

- EC2 #1: Intel Xeon Platinum 8259CL @ 2.5GHz, **4 vCPU / 15 GiB RAM / swap 0**, x86_64
  (2026-09-09 확인. 0909 문서 §3.1·일부 티켓은 `t4g.xlarge` ARM 전제 — 크기는 동급, arch만 x86)
- `onnxruntime` `CPUExecutionProvider`
- 처리량 (이 스펙 실측): 10만건 재임베딩 ~20.7분 (batch 32). flat cosine top-20 별도 ~110초 (S15P21A506-169).
  2단계 랭커는 retrieve-k 30 이라 검색 비용 소폭 증가 — 재측정 필요
- ⚠️ EC2 #1은 Spark(master+worker①, ~10G)·MinIO·MLflow·cron ETL과 공유. swap 0이라
  동시 실행 시 OOM 위험 → AI 배치는 Spark ETL과 시간이 겹치지 않게 cron 스케줄 분리 필요 (미정)

## 검증 기록 (2026-09-09, S15P21A506-287)

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

- 모델: MinIO `pickage-mlflow-artifacts/models/similar-packages/vN/` — `model.onnx` + `model.onnx.data` + tokenizer + `run_manifest.json` (+ `ref_emb.npy`). 버전당 ~265 MiB.
- 벡터: MinIO `pickage-vectors/vN/` — 10만 임베딩, 버전당 ~146 MiB.
- 학습 데이터: MinIO `pickage-curated/` — `train_combined_vN.jsonl`, `held_out_eval_bundle_vN.json`.
- MLflow 미배포(S15P21A506-236)라 당분간 수동 업로드.

**보관 정책**: `@production` + 직전 2개 버전만 유지 (그 이전은 삭제). AI 트랙 MinIO 용량 목표 **~2 GB, 상한 4 GB**. 디스크(320 GB)·계획 EBS(200 GB) 대비 무시 가능.
