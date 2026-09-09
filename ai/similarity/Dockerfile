# similarity-batch-pipeline — EC2 #1, cron(#1)이 배치 시각마다 새로 띄우는 1회성 배치 잡
# 대상 아키텍처: x86_64 (2026-09-09 EC2 #1에서 `uname -m` 확인).
#   0904 문서·일부 티켓은 t4g.xlarge(ARM64/Graviton) 전제로 쓰여 있으나 실제는 x86.
#   인프라팀에 최종 확정 확인 필요. 베이스 이미지는 멀티아치라 arch가 바뀌어도 빌드는 됨.
FROM python:3.11-slim-bookworm

# 파이썬 stdout 버퍼링 방지.
# 장애 인지가 별도 모니터링 스택 없이 `docker logs`에 의존하는 구조라,
# 로그가 늦게 찍히거나 컨테이너 종료 직전에 몰려 나오는 걸 막기 위함.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 의존성을 코드보다 먼저 복사해 레이어 캐시를 활용
# (코드만 바뀌었을 때 pip install을 다시 돌리지 않도록)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY similarity_batch_pipeline.py .

# non-root 사용자로 실행 (보안 관례 — 인프라팀 정책 확인되면 조정)
RUN useradd --create-home --uid 1000 appuser
USER appuser

# MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY / MLFLOW_TRACKING_URI 등은
# 여기서 하드코딩하지 않음 — 실행 시 인프라팀 배포 방식(compose env_file 등)으로 주입

# ENTRYPOINT 로 둔다 — 배치가 곧 --snapshot / --model-ver 같은 인자를 받으므로
#   docker run <img> --snapshot 2026-09-07
# 형태로 그대로 넘어가게 한다.
ENTRYPOINT ["python", "similarity_batch_pipeline.py"]