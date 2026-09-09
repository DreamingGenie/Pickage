"""분산과 MinIO 접속을 한 번에 증명하는 최소 잡.

두 노드에 Spark 를 올린 뒤 **가장 먼저** 돌린다. 실제 배치를 먼저 돌리면
실패했을 때 원인이 배치 로직인지 클러스터 배선인지 가릴 수 없다.

    spark-submit --master spark://<master>:7077 \
      --total-executor-cores 2 --executor-cores 1 --executor-memory 512m \
      /opt/work/spark/smoke_distribution.py

확인하는 것 넷:
  1. executor 가 **두 개 이상의 호스트**에 뜬다  ← 분산 증빙 (요구사항 10.1)
  2. s3a 로 MinIO 에 쓸 수 있다
  3. 쓴 것을 다시 읽을 수 있다
  4. executor 가 (driver 가 아니라) MinIO 에 직접 닿는다

4번이 중요하다. driver 만 MinIO 에 닿고 executor 는 못 닿는 상태에서도
1~3 번이 통과할 수 있다 — 파티션이 하나면 driver 쪽에서 다 처리되기 때문이다.
그래서 일부러 파티션을 여러 개로 나눠 쓴다.
"""

import socket
import sys

from pyspark.sql import SparkSession

PATH = "s3a://pickage-raw/_smoke/distribution-check"

spark = SparkSession.builder.appName("smoke-distribution").getOrCreate()
sc = spark.sparkContext

# ── 1. executor 가 어느 호스트에 떴나 ─────────────────────────────
# 태스크를 넉넉히 만들어 모든 executor 에 최소 하나는 가게 한다.
hosts = sorted(
    sc.parallelize(range(200), 16).map(lambda _: socket.gethostname()).distinct().collect()
)
print(f"EXECUTOR_HOSTS: {hosts}")

# ── 2~4. s3a 왕복 ────────────────────────────────────────────────
# repartition(4) 로 파티션을 나눠 **executor 가 직접** MinIO 에 쓰게 만든다.
df = spark.range(0, 1000).repartition(4)
df.write.mode("overwrite").parquet(PATH)

back = spark.read.parquet(PATH)
rows = back.count()
print(f"ROWS_READ_BACK: {rows}")

spark.stop()

# ── 판정 ────────────────────────────────────────────────────────
ok = True
if rows != 1000:
    print(f"FAIL: 1000 행을 기대했는데 {rows} 행이다")
    ok = False
if len(hosts) < 2:
    print(f"FAIL: executor 가 한 호스트에만 떴다 ({hosts}) — 분산이 성립하지 않았다")
    print("      worker 가 둘 다 등록됐는지, --total-executor-cores 가 충분한지 볼 것")
    ok = False

print("SMOKE_OK" if ok else "SMOKE_FAILED")
sys.exit(0 if ok else 1)
