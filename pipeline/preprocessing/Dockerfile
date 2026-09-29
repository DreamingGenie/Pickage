# Build context: pipeline/. Keep the existing ingest runtime unchanged.
FROM node:24-bookworm-slim AS node_runtime
FROM python:3.12-slim-bookworm
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node_runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
COPY minio/requirements.txt /tmp/pipeline/minio/requirements.txt
COPY preprocessing/curated/requirements.txt /tmp/pipeline/preprocessing/curated/requirements.txt
RUN pip install --no-cache-dir -r /tmp/pipeline/preprocessing/curated/requirements.txt \
 && useradd --create-home --uid 1000 pickage
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1
USER pickage
WORKDIR /opt/work
ENTRYPOINT ["python", "-m", "pipeline.preprocessing.orchestration.dispatcher"]
