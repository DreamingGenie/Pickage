# Spark 실행 전에 읽히는 환경 설정 (spark-submit · pyspark 가 자동으로 source 한다).
#
# MinIO 자격증명은 pipeline/minio/.env 에 MINIO_ROOT_* 이름으로 들어 있고,
# s3a 는 AWS_* 이름을 읽는다. 여기서 이름만 바꿔 넘긴다.
# 이렇게 하면 .env 에 같은 값을 두 벌 적지 않아도 된다.
export AWS_ACCESS_KEY_ID="${MINIO_ROOT_USER}"
export AWS_SECRET_ACCESS_KEY="${MINIO_ROOT_PASSWORD}"

# driver 가 광고할 주소. .env 의 PRIVATE_IP 를 쓴다.
# 이게 없으면 Spark 가 인터페이스를 자동 선택하는데, 이 서버에는 docker0(172.17.0.1)도
# 있어서 그쪽을 고를 수 있다. 그러면 다른 호스트의 executor 가 driver 를 못 찾는다.
# 값이 있을 때만 내보낸다. 비워 두면 Spark 의 자동 탐지에 맡긴다 —
# 한 호스트 안에서만 도는 리허설에서는 그게 맞다.
if [ -n "${PRIVATE_IP:-}" ]; then
  export SPARK_LOCAL_IP="${PRIVATE_IP}"
fi

# worker RPC 포트는 각 노드의 compose.yaml 에서 --port 로 넘긴다.
# 여기에도 두면 두 군데가 갈라질 수 있어 한 곳으로 모았다.
