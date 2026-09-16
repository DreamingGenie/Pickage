"""export_onnx_v7.py — merged_bge_v7 PyTorch 모델을 ONNX로 export.

merge_and_export_onnx_v6.py 의 4~5단계(export_onnx, onnx_sanity_check)를 그대로 따른다
(같은 exporter 옵션 — 이게 v6에서 "PyTorch vs ONNX 오차 0.000000"을 낸 검증된 방식).

사전조건: merge_lora_v7.py 로 이미 병합된 PyTorch 모델 디렉터리가 있어야 함.
  python merge_lora_v7.py --adapter ./lora_final_v7_full10ep --out ./merged_bge_v7_final

ai/MODEL_CONTRACT.md 의 v6 export 방식과 동일:
  - torch.onnx.export, legacy TorchScript exporter (dynamo=False), opset 18
  - BertModel 을 2입력(input_ids, attention_mask)·1출력(last_hidden_state) wrapper로 감쌈
  - dynamic_axes: 전부 {0: batch_size, 1: sequence_length}
  - 후처리(CLS pooling + L2 정규화)는 ONNX 밖 — 배치 코드(similarity_batch_pipeline.py)가 함
"""
import argparse
import os
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoTokenizer

# 실제 149 설계(description + keyword 결합) 포맷과 맞춰 몇 개 샘플로 확인
TEST_TEXTS = [
    "DESCRIPTION: Fast, low-overhead logging library for Node.js. / KEYWORDS: logger, json, pino",
    "DESCRIPTION: Promise based HTTP client for the browser and node.js. / KEYWORDS: http, fetch, promise",
    "DESCRIPTION: Deprecated, use fastify instead. / KEYWORDS: server, http, deprecated",
]


def embed_st(model, texts):
    with torch.no_grad():
        return model.encode(texts, convert_to_tensor=True, normalize_embeddings=True)


class OnnxWrapper(torch.nn.Module):
    """변환기가 헷갈리지 않게 입력 2개·출력 1개(last_hidden_state)로 고정."""

    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask):
        out = self.model(input_ids=input_ids, attention_mask=attention_mask)
        return out.last_hidden_state


def export_onnx(merged_dir, onnx_dir):
    os.makedirs(onnx_dir, exist_ok=True)
    export_model = AutoModel.from_pretrained(merged_dir)
    tokenizer = AutoTokenizer.from_pretrained(merged_dir)
    export_model.eval()
    wrapper = OnnxWrapper(export_model).eval()

    dummy = tokenizer(
        TEST_TEXTS[:1], padding="max_length", truncation=True, max_length=32, return_tensors="pt"
    )
    with torch.no_grad():
        torch.onnx.export(
            wrapper,
            (dummy["input_ids"], dummy["attention_mask"]),
            f"{onnx_dir}/model.onnx",
            input_names=["input_ids", "attention_mask"],
            output_names=["last_hidden_state"],
            dynamic_axes={
                "input_ids": {0: "batch_size", 1: "sequence_length"},
                "attention_mask": {0: "batch_size", 1: "sequence_length"},
                "last_hidden_state": {0: "batch_size", 1: "sequence_length"},
            },
            opset_version=18,
            dynamo=False,
        )
    tokenizer.save_pretrained(onnx_dir)
    print(f"[export] ONNX export 완료: {onnx_dir}")


def onnx_sanity_check(merged_dir, onnx_dir, pytorch_embeddings):
    import onnxruntime as ort

    tokenizer = AutoTokenizer.from_pretrained(merged_dir)
    sess = ort.InferenceSession(f"{onnx_dir}/model.onnx")
    input_names = {i.name for i in sess.get_inputs()}

    inputs = tokenizer(TEST_TEXTS, padding=True, truncation=True, return_tensors="np")
    onnx_inputs = {k: v for k, v in inputs.items() if k in input_names}
    outputs = sess.run(None, onnx_inputs)

    # bge는 CLS 토큰 pooling — MODEL_CONTRACT.md 후처리 규격과 동일
    onnx_embeddings = outputs[0][:, 0, :]
    onnx_embeddings = onnx_embeddings / np.linalg.norm(onnx_embeddings, axis=1, keepdims=True)

    diff = np.abs(pytorch_embeddings.cpu().numpy() - onnx_embeddings).max()
    print(f"[check:onnx] PyTorch(merged) vs ONNX 최대 절대 오차: {diff:.6f}")
    if diff > 1e-3:
        print("[check:onnx] 경고: 오차가 큼 — pooling 방식/precision 차이 재확인 필요")
    else:
        print("[check:onnx] 통과")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged", default="./merged_bge_v7_final",
                     help="merge_lora_v7.py 로 병합해둔 PyTorch 모델 디렉터리")
    ap.add_argument("--onnx-dir", default="./onnx_bge_v7")
    args = ap.parse_args()

    print(f"1) merged 모델 로드 (참조 임베딩용) — {args.merged}")
    model = SentenceTransformer(args.merged)
    ref = embed_st(model, TEST_TEXTS)
    del model

    print("2) ONNX export")
    export_onnx(args.merged, args.onnx_dir)

    print("3) ONNX 결과 검증 (PyTorch vs ONNX)")
    onnx_sanity_check(args.merged, args.onnx_dir, ref)

    print(f"\n완료. {args.onnx_dir}/ 에 model.onnx + model.onnx.data + tokenizer.json + "
          f"tokenizer_config.json 있는지 확인. 오차 통과했으면 MinIO 업로드 준비 OK.")
