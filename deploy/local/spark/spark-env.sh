# Spark 실행 전에 읽히는 환경 설정 (spark-submit · pyspark 가 자동으로 source 한다).
#
# MinIO 자격증명은 pipeline/minio/.env 에 MINIO_ROOT_* 이름으로 들어 있고,
# s3a 는 AWS_* 이름을 읽는다. 여기서 이름만 바꿔 넘긴다.
# 이렇게 하면 .env 에 같은 값을 두 벌 적지 않아도 된다.
export AWS_ACCESS_KEY_ID="${MINIO_ROOT_USER}"
export AWS_SECRET_ACCESS_KEY="${MINIO_ROOT_PASSWORD}"
