# 운영 Spark 설정 (양 노드 공용)

| 파일 | 무엇 |
| --- | --- |
| `spark-defaults.conf` | s3a(MinIO) 접속과 hadoop-aws 버전. **두 노드가 같은 파일을 마운트한다** |
| `spark-env.sh` | `MINIO_ROOT_*` 을 s3a 가 읽는 `AWS_*` 이름으로 바꿔 준다 |

## 로컬 설정과 다른 점 하나

`spark.hadoop.fs.s3a.endpoint` 가 서비스 이름이 아니라 **`data` 노드의 사설 IP** 다.

```
로컬   http://minio:9000              ← 같은 compose 네트워크
운영   http://172.26.8.249:9000       ← 다른 호스트에서도 닿아야 한다
```

`app` 노드의 worker② 는 `data` 노드의 compose 네트워크 밖에 있어서 `minio` 라는
이름을 풀 수 없다. 그래서 MinIO 가 루프백 외에 **사설 IP 에도 바인딩**되어 있다
(`deploy/prod/data/compose.yaml` 의 `PRIVATE_IP`).

## 왜 커스텀 이미지를 만들지 않나

`spark.jars.packages` 로 받은 jar 는 **driver 가 executor 에 배포한다.**
worker 노드에 미리 심어 둘 필요가 없다.

레지스트리가 없는 구성에서는 두 노드에 같은 커스텀 이미지를 옮길 방법이 없다 —
버전이 어긋나면 배치가 **조용히 멈춘다.** 공개 이미지 + `packages` 조합이 그 문제를 피한다.

대신 **driver 노드에 인터넷이 필요하다.** 첫 실행에서 Maven 에서 받아
`spark.jars.ivy` 캐시에 쌓는다.
