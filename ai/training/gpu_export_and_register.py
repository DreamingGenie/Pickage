"""gpu_export_and_register.py — ONNX 모델을 (필요하면 MinIO에 올리고) MLflow에 등록.

run_pipeline.sh --register-only 의 5단계(register_mlflow)가 부르는 스크립트.
두 가지 쓰임이 있다.

1) 이미 MinIO에 올라가 있는 모델을 등록만 할 때 (예: v7 — 웹 콘솔로 이미 업로드됨,
   경로도 pickage-mlflow-artifacts/v7/ 로 정리돼 있음)

     MLFLOW_TRACKING_URI=http://127.0.0.1:5000 python gpu_export_and_register.py --version v7

   --onnx-dir 를 안 주면 업로드를 건너뛰고 s3://<bucket>/<version> 를 그대로 새 model
   version으로 등록한다 (재전송 중 손상 위험 없이, 이미 검증된 파일을 그대로 쓴다).

2) 로컬 ONNX 산출물을 올리면서 같이 등록할 때 (예: 다음 v2clean)

     python gpu_export_and_register.py --version v7-v2clean --onnx-dir ./onnx_bge_v7_v2clean

   model.onnx·tokenizer.json·tokenizer_config.json·run_manifest.json 을 순서대로 올리고
   마지막에 빈 _SUCCESS 를 써서 "업로드 완료" 표시를 남긴다 (deploy/prod/data/README.md 의
   "산출물 경로에 _SUCCESS 가 있으면 끝난 것" 관례와 동일).

등록 이름·별칭은 deploy/prod/data/.env.example 의 AI_MODEL_NAME·AI_MODEL_ALIAS 와 반드시
같아야 한다 — run-similarity-batch.sh 가 그 이름으로 MLflow 에 물어서 배치를 돌린다.
기본값 pickage-similarity / production.

실행 위치: MLflow가 도는 data 노드(EC2 #1)에서 직접 돌리면 터널 없이
MLFLOW_TRACKING_URI=http://127.0.0.1:5000 로 바로 붙는다. GPU 서버(jupyter05)에서
돌리려면 run_pipeline.sh 의 SSH 터널을 먼저 열고 http://localhost:5000 을 쓴다.

--onnx-dir 를 줄 때만 MinIO 자격증명이 필요하다 (환경변수):
  MINIO_ENDPOINT_URL (예: http://127.0.0.1:9000, 터널 경유 시 http://localhost:9000)
  MINIO_ACCESS_KEY / MINIO_SECRET_KEY

⚠ run_pipeline.sh 의 REGISTER_CMD 기본값(`--onnx $ONNX_DIR`)은 이 스크립트의 인자
(`--version` 필수)와 다르다. run_pipeline.sh 자체가 아직 스텁 상태(EC2_HOST 미확정 등)라
이번 v7 등록에는 이 스크립트를 직접 호출했고, run_pipeline.sh 쪽 연결은 별도 작업으로 남긴다.
"""
import argparse
import os

from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

UPLOAD_FILES = ["model.onnx", "tokenizer.json", "tokenizer_config.json", "run_manifest.json"]


def upload_to_minio(onnx_dir, bucket, version):
    import boto3
    from botocore.client import Config

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["MINIO_ENDPOINT_URL"],
        aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
        aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
        config=Config(s3={"addressing_style": "path"}),  # MinIO는 virtual-host style 응답 안 함
    )
    for fname in UPLOAD_FILES:
        local_path = os.path.join(onnx_dir, fname)
        if not os.path.exists(local_path):
            raise SystemExit(
                f"[upload] 없음: {local_path} — model.onnx/tokenizer.json/"
                f"tokenizer_config.json/run_manifest.json 4개가 다 있어야 한다."
            )
        key = f"{version}/{fname}"
        print(f"[upload] {local_path} → s3://{bucket}/{key}")
        s3.upload_file(local_path, bucket, key)

    # _SUCCESS 는 맨 마지막에 — 배치 스크립트가 이걸로 "업로드 완료"를 판단한다
    s3.put_object(Bucket=bucket, Key=f"{version}/_SUCCESS", Body=b"")
    print(f"[upload] s3://{bucket}/{version}/_SUCCESS 게시")


def ensure_registered_model(client, name):
    try:
        client.create_registered_model(name)
        print(f"[register] 등록 모델 '{name}' 새로 생성")
    except MlflowException as e:
        if e.error_code != "RESOURCE_ALREADY_EXISTS":
            raise


def register_and_promote(tracking_uri, bucket, version, model_name, alias):
    client = MlflowClient(tracking_uri=tracking_uri)
    ensure_registered_model(client, model_name)

    source = f"s3://{bucket}/{version}"
    mv = client.create_model_version(name=model_name, source=source, run_id=None)
    print(f"[register] {model_name} v{mv.version} 등록 — source={source}")

    client.set_registered_model_alias(model_name, alias, mv.version)
    print(f"[register] alias '{alias}' → v{mv.version}")
    return client, mv.version


def verify(client, model_name, alias):
    mv = client.get_model_version_by_alias(model_name, alias)
    print(f"[verify] {model_name}@{alias} → v{mv.version}  source={mv.source}")
    return mv


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ONNX 모델을 (필요하면 업로드하고) MLflow 에 등록 + production 승격"
    )
    ap.add_argument("--version", required=True,
                     help="MinIO 경로 세그먼트 — s3://<bucket>/<version> (예: v7)")
    ap.add_argument("--onnx-dir", default=None,
                     help="주면 이 로컬 디렉터리를 먼저 MinIO 에 업로드한다. "
                          "생략하면 이미 올라가 있다고 보고 등록만 한다.")
    ap.add_argument("--bucket", default="pickage-mlflow-artifacts")
    ap.add_argument("--model-name", default="pickage-similarity",
                     help="deploy/prod/data/.env.example 의 AI_MODEL_NAME 과 일치해야 함")
    ap.add_argument("--alias", default="production",
                     help="deploy/prod/data/.env.example 의 AI_MODEL_ALIAS 와 일치해야 함")
    ap.add_argument("--tracking-uri", default=None,
                     help="생략하면 MLFLOW_TRACKING_URI 환경변수 사용")
    args = ap.parse_args()

    tracking_uri = args.tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        raise SystemExit("MLFLOW_TRACKING_URI 환경변수를 설정하거나 --tracking-uri 를 넘기세요.")

    if args.onnx_dir:
        upload_to_minio(args.onnx_dir, args.bucket, args.version)

    client, new_version = register_and_promote(
        tracking_uri, args.bucket, args.version, args.model_name, args.alias
    )
    verify(client, args.model_name, args.alias)

    print(f"\n완료. {args.model_name}@{args.alias} → v{new_version} "
          f"(source=s3://{args.bucket}/{args.version})")
