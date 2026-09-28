# 파이프라인 모니터 런타임. 두 노드의 모니터링 스택이 상주 컨테이너로 띄운다
# (deploy/prod/monitoring/<노드>/compose.yaml 의 pipeline-monitor).
#
# ── 이 이미지에는 코드가 없다 ─────────────────────────────────
# ../Dockerfile(주간 수집 런타임)과 같은 이유다 — 노드에 레지스트리가 없어서 코드를 구우면
# 한 줄 고칠 때마다 서버에서 다시 빌드해야 한다. `pipeline/` 은 compose 가 마운트한다.
# 의존성(boto3·PyYAML)이 바뀔 때만 다시 굽는다:  docker compose build pipeline-monitor
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# uid 1000 으로 돈다. 호스트의 ubuntu 와 같은 uid 라 마운트한 산출물 디렉터리를 그대로 읽는다.
# 아무것도 쓰지 않는 컨테이너다 — 보고서는 물을 때 만들어 HTTP 로 답하고 끝이다.
RUN useradd --create-home --uid 1000 pickage \
 && install -d -o pickage -g pickage /opt/work

USER pickage
WORKDIR /opt/work

# 인자가 그대로 넘어간다:  docker compose run --rm pipeline-monitor --once
ENTRYPOINT ["python", "-m", "pipeline.monitor.run"]
