"""merge_lora_v7.py — lora_final_v7_hiconf 어댑터를 base(BAAI/bge-small-en-v1.5)에 병합.

merge_and_export_onnx_v6.py 의 1~3단계(로드→병합→저장)를 그대로 따른다 — 그 스크립트
docstring 에 검증된 이유가 적혀 있음: get_peft_model() 은 forward path 에 안 걸리는
버그가 있어(ST Transformer.auto_model 이 읽기전용 property), model.add_adapter()/
load_adapter() (transformers 네이티브, in-place 주입) + 레이어 단위
BaseTunerLayer.merge() 조합만 안전하다.

그래서 SentenceTransformer("./lora_final_v7_hiconf") 로 바로 여는 걸 쓰지 않는다 —
그 경로가 이 in-place 주입과 같은 방식으로 동작한다는 보장이 없다 (v6 때도 이 이유로
base 를 새로 열고 load_adapter() 를 명시적으로 호출했음).

ONNX export 는 이 단계에서 안 함 — recall 평가(eval_recall.py)는 PyTorch 병합 모델만
있으면 되고, ONNX export 는 배포 확정 후 별도(merge_and_export_onnx_v6.py 패턴 재사용).
"""
import argparse
import torch
from sentence_transformers import SentenceTransformer
from peft.tuners.tuners_utils import BaseTunerLayer

BASE_MODEL = "BAAI/bge-small-en-v1.5"

TEST_TEXTS = [
    "DESCRIPTION: Fast, low-overhead logging library for Node.js. / KEYWORDS: logger, json, pino",
    "DESCRIPTION: Promise based HTTP client for the browser and node.js. / KEYWORDS: http, fetch, promise",
]


def load_finetuned_model(adapter_dir):
    model = SentenceTransformer(BASE_MODEL)
    transformer_module = model[0].auto_model
    transformer_module.load_adapter(adapter_dir)
    model.eval()
    return model


def embed(model, texts):
    with torch.no_grad():
        return model.encode(texts, convert_to_tensor=True, normalize_embeddings=True)


def merge_lora_layers(model):
    merged_count = 0
    for module in model[0].auto_model.modules():
        if isinstance(module, BaseTunerLayer):
            module.merge()
            merged_count += 1
    print(f"[merge] LoRA 레이어 {merged_count}개 병합 완료")
    if merged_count == 0:
        raise RuntimeError(
            "병합할 LoRA 레이어를 못 찾음 — target_modules 설정이나 "
            "adapter 로딩 경로(model[0].auto_model)가 실제 구조와 다를 수 있음"
        )
    return model


def sanity_check(before, after, atol=1e-4):
    diff = (before - after).abs().max().item()
    print(f"[check:merge] 최대 절대 오차: {diff:.6f}")
    if diff > atol:
        raise RuntimeError(
            f"[check:merge] 병합 전/후 임베딩이 다름 (허용치 {atol} 초과). "
            "load_adapter 경로가 학습 때 구조와 어긋났을 가능성."
        )
    print("[check:merge] 통과")


def merge_from_checkpoint(adapter_dir, verbose=True):
    """체크포인트(어댑터) 하나를 로드→병합해서 메모리 상의 모델 객체로 반환.
    디스크에 저장하지 않음 — sweep_checkpoints.py 처럼 여러 체크포인트를 빠르게
    돌려볼 때, 매번 save/load 왕복하지 않으려고 분리한 함수."""
    model = load_finetuned_model(adapter_dir)
    before = embed(model, TEST_TEXTS)
    model = merge_lora_layers(model)
    after = embed(model, TEST_TEXTS)
    diff = (before - after).abs().max().item()
    if verbose:
        print(f"[merge:{adapter_dir}] 병합 전/후 오차 {diff:.6f}")
    if diff > 1e-4:
        raise RuntimeError(f"[{adapter_dir}] 병합 전/후 임베딩이 다름 (오차 {diff:.6f})")
    return model


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default="./lora_final_v7_hiconf", help="LoRA 어댑터 디렉터리 (학습 결과 또는 체크포인트)")
    ap.add_argument("--out", default="./merged_bge_v7_hiconf", help="병합된 모델을 저장할 디렉터리")
    args = ap.parse_args()

    print(f"1) 파인튜닝 모델 로드 (adapter 활성 상태) — {args.adapter}")
    model = load_finetuned_model(args.adapter)
    before = embed(model, TEST_TEXTS)

    print("2) LoRA 레이어 병합")
    model = merge_lora_layers(model)
    after = embed(model, TEST_TEXTS)
    sanity_check(before, after)

    print("3) 병합된 모델 저장")
    model.save(args.out)
    print(f"완료 — {args.out} 저장됨. eval_recall.py --model {args.out} 로 평가 가능.")
