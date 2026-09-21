# MinIO 접근 정책

계정이 **무엇을 할 수 있는지** 규정하는 파일이다. 터미널에 친 명령은 흔적이 안 남지만
이건 리뷰에 올라오고 나중에 똑같이 다시 적용할 수 있다. 그래서 커밋한다.

| 파일 | 누가 쓰나 | 무엇이 되나 |
| --- | --- | --- |
| `gpu.json` | 외부 GPU 서버 (`pickage-gpu`) | `pickage-raw` · `pickage-curated` **읽기** + `pickage-mlflow-artifacts` **쓰기** |
| `ops.json` | app 노드 api (`pickage-ops`) | `pickage-raw` 의 `_ops/weekly/` **읽기** + `manual-request.json` **쓰기** |
| `similarity-loader.json` | app 노드 similarity-loader (`pickage-similarity-loader`) | `pickage-vectors` **읽기만**. 쓰기·삭제 없다 |
| `api-loader.json` | app 노드 `package-env-loader` (`pickage-api-loader`) | `pickage-curated` **읽기만**. 쓰기·삭제 없다 |

적용 방법은 [deploy/prod/data/README.md](../../../deploy/prod/data/README.md) 의
"GPU 서버용 계정" · "app 노드 api 에 줄 계정" ·
"app 노드 similarity-loader 에 줄 계정" · "app 노드 백엔드 로더에 줄 계정".

**소비자마다 계정을 따로 둔다.** 하나로 합치면 권한이 그중 가장 넓은 것으로 수렴하고,
유출 시 무엇을 폐기해야 하는지도 흐려진다 — 폐기는 계정 하나 지우는 것이어야 한다.

## 읽는 법

`ListBucket` 은 **버킷 ARN** 에, `GetObject` 는 **객체 ARN(`/*`)** 에 건다.
둘 다 있어야 "목록을 보고 받아간다" 가 성립한다 — 하나만 있으면 목록은 보이는데
못 받거나, 키를 정확히 알아야만 받아진다.

`GetBucketLocation` 은 boto3 가 첫 요청 전에 부른다. 없으면 인증은 통과하는데
클라이언트가 먼저 죽는다.

**멀티파트는 권한이 따로다.** `AbortMultipartUpload`·`ListMultipartUploadParts` 는 객체
ARN 에, `ListBucketMultipartUploads` 는 버킷 ARN 에 건다. 빠뜨리면 **작은 파일은 올라가고
큰 파일만 `AccessDenied`** 가 난다 — 권한 문제로 안 보여서 진단이 오래 걸린다.
132 MiB 모델이 정확히 그 경우다.

## 왜 읽기는 두 버킷 다 주나

원래는 `curated` 만 주려 했다. 소비자는 가공된 것만 보게 하는 편이 사고 반경이 작다.
그런데 학습에 필요한 값(예: keywords)이 `raw` 에만 있는 경우가 실제로 나왔고,
읽기에서는 **버킷을 골라 주는 비용이 얻는 것보다 크다** — 필요해질 때마다 정책을
고치고 재적용하고 쓰는 쪽에 다시 알려야 한다.

## 경계는 쓰기에서 지킨다

**어떤 소비자에게도 `raw`·`curated` 쓰기는 주지 않는다.** `raw` 는 유일본이고
npm 다운로드 수처럼 **소급 조회가 안 되는 것**이 섞여 있다.

GPU 에 쓰기를 준 곳은 `pickage-mlflow-artifacts` **하나뿐**이고, 거기 있는 것은
**다시 만들 수 있는 학습 산출물**이다. 원본 보호라는 원칙은 그대로다.

**삭제는 아무 버킷에도 주지 않는다.** 모델은 버전마다 새 경로에 쌓이므로 지울 일이 없고,
보관 정책에 따른 정리는 루트로 한다.
