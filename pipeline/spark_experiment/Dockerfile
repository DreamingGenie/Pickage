# Local comparison: BOTH engines use this same image and CPU/memory caps.
# Production cluster continues using its existing deployment until an explicit rollout.
ARG NODE_IMAGE=node:24-bookworm-slim
ARG SPARK_IMAGE=apache/spark@sha256:936ff39fd63e2bb5ed064f0fbe1518198473f1cdbfa2f863d087a9a8e58116ba
FROM ${NODE_IMAGE} AS node_runtime
FROM ${SPARK_IMAGE} AS spark_runtime
FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless procps && rm -rf /var/lib/apt/lists/*
COPY --from=spark_runtime /opt/spark /opt/spark
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node_runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN pip3 install --no-cache-dir duckdb==1.5.5 boto3==1.43.89
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 SPARK_HOME=/opt/spark
ENV PATH=/opt/spark/bin:/usr/local/bin:/usr/bin:/bin
ENV PYSPARK_PYTHON=/usr/local/bin/python3 PYSPARK_DRIVER_PYTHON=/usr/local/bin/python3
ENV PYTHONPATH=/workspace:/opt/spark/python:/opt/spark/python/lib/py4j-0.10.9.7-src.zip PYTHONDONTWRITEBYTECODE=1
WORKDIR /workspace
