# GPU 서버에서 MinIO 쓰기 (인수인계)

학습 데이터를 가져가고 **모델을 올리는** 쪽이 볼 문서다.

| | |
| --- | --- |
| 읽기 | `pickage-raw` · `pickage-curated` |
| **쓰기** | **`pickage-mlflow-artifacts` 만** (학습 산출물 업로드) |
| 못 하는 것 | `pickage-raw`·`pickage-curated` 에 쓰기, **모든 삭제**, 그리고 `pickage-vectors` · `pickage-quarantine` |
| 자격증명 | 별도 전달 (이 문서에 적지 않는다) |

## ⚠ 1. 먼저 터널을 연다 — 이게 없으면 아무것도 안 된다

MinIO 는 **인터넷에 열려 있지 않다.** 서버 루프백과 VPC 사설 IP 에만 붙어 있어서,
GPU 서버에서 바로 붙으면 연결이 안 된다. SSH 터널로 뚫는다.

```bash
ssh -N -L 9000:localhost:9000 <user>@j15a506a.p.ssafy.io
```

`-N` 은 셸을 안 열고 터널만 유지한다. **이 터널이 살아 있는 동안만** 접근된다.
다운로드가 오래 걸리면 `tmux` 나 `screen` 안에서 돌리거나 `-f` 로 백그라운드에 둘 것.

터널을 연 뒤 GPU 서버에서 보는 주소는 **`http://localhost:9000`** 이다.

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:9000/minio/health/live   # 200
```

> 200 이 안 나오면 자격증명 문제가 아니라 **터널 문제**다. 코드를 고치기 전에 여기부터 볼 것.

## ⚠ 2. path-style 을 켜야 한다 — 제일 많이 막히는 곳

boto3 · s3fs · Spark 의 기본값은 **virtual-host style**(`http://버킷명.endpoint/`)이고
MinIO 는 그 주소로 응답하지 않는다. 그냥 붙이면 DNS 오류나 404 가 난다.

```python
import boto3
from boto3.session import Config

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="...",
    aws_secret_access_key="...",
    config=Config(s3={"addressing_style": "path"}),   # ← 이 줄이 핵심
)

# 목록
for o in s3.list_objects_v2(Bucket="pickage-curated").get("Contents", []):
    print(o["Key"], o["Size"])

# 받기
s3.download_file("pickage-curated", "<키>", "/local/path.parquet")
```

pandas·pyarrow 로 바로 읽으려면 `s3fs` 를 쓴다.

```python
import s3fs, pyarrow.parquet as pq

fs = s3fs.S3FileSystem(
    key="...", secret="...",
    client_kwargs={"endpoint_url": "http://localhost:9000"},
    config_kwargs={"s3": {"addressing_style": "path"}},
)
df = pq.ParquetDataset("pickage-curated/<경로>", filesystem=fs).read().to_pandas()
```

Spark 라면 `fs.s3a.path.style.access=true` 와 `fs.s3a.endpoint=http://localhost:9000`.

## 3. 무엇이 어디 있나

| 버킷 | 무엇 |
| --- | --- |
| `pickage-raw` | 수집한 **원본** Parquet. 가공 전 값이 필요할 때 |
| `pickage-curated` | 정제·가공 결과. `package` · `version` 적재용 Parquet, ID 매핑, 품질 검증 결과 |
| `pickage-mlflow-artifacts` | **여기에만 쓴다.** 학습 산출물(ONNX·tokenizer·manifest) |

버킷별 역할은 [README.md](README.md), curated 의 컬럼 스키마는
[../curated/README.md](../curated/README.md) 에 있다.

경로 규칙은 데이터를 넣는 쪽이 정하므로, 실제 키는 목록으로 확인하는 게 빠르다.

```python
for o in s3.list_objects_v2(Bucket="pickage-raw", MaxKeys=20).get("Contents", []):
    print(o["Key"])
```

## 4. 모델 올리기

`pickage-mlflow-artifacts` **에만** 쓸 수 있다. 학습 산출물은 여기로 올린다.

```python
s3.upload_file("/local/onnx_bge_v7/model.onnx",
               "pickage-mlflow-artifacts", "onnx_bge_v7/model.onnx")
```

MLflow 로 등록하면 클라이언트가 **이 버킷에 직접** 올린다(서버가 중계하지 않는다).
그때 필요한 환경변수는 `deploy/prod/data/README.md` 의 "MLflow" 절에 있다.

> **큰 파일은 멀티파트로 올라간다.** 132 MiB 모델이 그렇다. 정책에 멀티파트 권한이
> 들어 있으니 그냥 되지만, **작은 파일만 되고 모델만 AccessDenied** 가 나면
> 그 권한이 빠진 것이다 — 인프라에 말할 것.

## 5. 안 되는 것과 그 이유

| 시도 | 결과 |
| --- | --- |
| `pickage-raw` · `pickage-curated` 에 쓰기 | **AccessDenied** |
| **삭제** (어느 버킷이든) | **AccessDenied** |
| `pickage-vectors` · `pickage-quarantine` | **AccessDenied.** 필요해지면 말할 것 |

**원본에 못 쓰는 것이 이 계정의 핵심이다.** `pickage-raw` 는 수집 원본의 유일본이고,
npm 다운로드 수처럼 **놓친 기간을 소급 조회할 수 없는 것**이 섞여 있다.
쓰기를 얹은 뒤에도 그 보장은 그대로다 — 쓰기가 열린 곳은
`pickage-mlflow-artifacts` 하나뿐이고, 거기 있는 것은 **다시 만들 수 있는 학습 산출물**이다.

삭제를 안 준 이유도 같다. 모델은 버전마다 새 경로에 쌓이므로 GPU 가 지울 일이 없고,
보관 정책(`@production` + 직전 2개)에 따른 정리는 인프라가 한다.

## 6. 키를 잃었거나 새어 나갔으면

바로 말할 것. **키 하나만 폐기하면 되고 다른 것에 영향이 없다** — 그러라고 별도 계정으로
만들어 둔 것이다. 새 키 발급도 명령 한 줄이다.
