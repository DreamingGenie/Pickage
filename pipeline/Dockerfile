# 주간 수집 회차를 돌리는 런타임. data 노드(j15a506a)의 systemd 타이머가
# `docker compose run --rm ingest-weekly` 로 10분마다 띄운다. 상주 서비스가 아니다.
#
# 절차와 각 단계의 함정: pipeline/weekly/README.md · deploy/prod/data/README.md
#
# ── 이 이미지에는 코드가 없다 ─────────────────────────────────
#
# 파이썬 런타임·gcloud CLI·의존성만 굽고, `pipeline/` 과 `datasets/` 는 저장소에서
# **마운트**한다. 같은 노드의 spark-worker-1 이 `../../../pipeline:/opt/work` 로 하는
# 방식과 같다. 이유가 셋이다.
#
#   1. **이 노드에는 CI 배포 러너도 레지스트리도 없다.** 코드를 구우면 한 줄 고칠 때마다
#      서버에 들어가 `docker compose build` 를 해야 한다.
#   2. `pipeline/minio/ingest_raw.py` 의 client() 가 자격증명을 **파일**에서 읽는다
#      (`pipeline/minio/<PICKAGE_MINIO_ENV>`). 그 파일은 .gitignore 대상이라 구울 수 없다.
#   3. 입고기가 대상 CSV(`datasets/targets/…`)를 루트 레벨 실파일로 요구하고 심링크를
#      거부한다(`_assert_no_symlink`). 저장소가 통째로 보이는 편이 단순하다.
#
# **대신 포기하는 것**: 이미지 태그가 거동을 못 박지 못한다. api·web 은 태그가 가리키는
# 이미지가 곧 배포본이라 롤백이 태그 교체지만, 여기서는 **롤백이 `git checkout`** 이다.
# 이미지는 의존성이 바뀔 때만 다시 빌드한다.
FROM python:3.12-slim-bookworm

# 로그가 늦게 찍히거나 종료 직전에 몰려 나오는 것을 막는다. 장애 인지가 단계별 로그
# 파일과 `docker logs` 에 달려 있다.
ENV PYTHONUNBUFFERED=1
# Windows 에서 개발할 때 출력을 파일로 돌리면 기본 인코딩이 cp949 가 되어 em dash 한
# 글자에 프로세스가 죽는다. 서버에서는 무해하고, 두 환경의 동작을 같게 만든다.
ENV PYTHONIOENCODING=utf-8

# ── gcloud CLI ────────────────────────────────────────────────
#
# gcs_sync 단계가 `gcloud storage rsync` 를 부른다. BigQuery 는 파이썬 클라이언트로
# 가지만 GCS 내려받기는 CLI 라 둘 다 필요하다.
#
# ⚠ **인증 경로가 둘이다.** google-cloud-bigquery 는 GOOGLE_APPLICATION_CREDENTIALS 를
#   보고, gcloud 는 자체 자격증명 저장소를 본다. 아래 ENV 에서 둘 다 세운다.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
 && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
      | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg]" \
      "https://packages.cloud.google.com/apt cloud-sdk main" \
      > /etc/apt/sources.list.d/google-cloud-sdk.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends google-cloud-cli \
 && apt-get purge -y gnupg \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# 의존성을 코드보다 먼저 넣어 레이어 캐시를 쓴다 — 여기서는 코드가 아예 안 들어오지만,
# requirements 두 개가 각각 언제 바뀌는지 보이게 나눠 둔다.
#   collectors  BigQuery·GCS·requests·pyarrow·duckdb  (원천 수집기)
#   minio       boto3·duckdb                          (입고기와 상태 계층)
COPY collectors/requirements.txt /tmp/collectors-requirements.txt
COPY minio/requirements.txt /tmp/minio-requirements.txt
RUN pip install --no-cache-dir -r /tmp/collectors-requirements.txt \
                                 -r /tmp/minio-requirements.txt \
 && rm /tmp/collectors-requirements.txt /tmp/minio-requirements.txt

# ⚠ **uid 1000 으로 돈다.** 산출물이 호스트 바인드(/srv/pickage/ingest-work)에 쌓이는데,
#   root 로 쓰면 그 파일을 호스트의 ubuntu 계정이 못 지운다 — 지난 회차 정리가 거기서
#   막힌다. 바인드 디렉터리를 uid 1000 소유로 만들어 두어야 한다(README 에 명령이 있다).
RUN useradd --create-home --uid 1000 pickage
USER pickage

# 저장소가 여기 마운트된다. pipeline/minio/ingest_raw.py 가 ROOT 를 __file__ 기준
# parents[2] 로 잡으므로, 산출물 바인드는 반드시 **이 경로의 data/** 여야 한다.
WORKDIR /opt/work

# 인증 경로 둘. 값은 compose 가 넘기는 키 파일 하나를 함께 가리킨다.
#   GOOGLE_APPLICATION_CREDENTIALS          파이썬 클라이언트(BigQuery·GCS)
#   CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE  gcloud CLI
#
# ⚠ 빌드할 때 `SecretsUsedInArgOrEnv` 경고가 뜬다. **오탐이다** — 이름에 CREDENTIALS 가
#   들어가서 걸리는 것이고 값은 비밀이 아니라 경로다. 키 자체는 이미지에 들어가지 않고
#   compose 가 /srv/pickage/secrets 를 읽기 전용으로 마운트한다. 경고를 없애겠다고 이
#   줄을 지우면 gcloud 가 인증을 못 찾는다.
ENV GOOGLE_APPLICATION_CREDENTIALS=/opt/work/secrets/gcp-service-account.json
ENV CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE=/opt/work/secrets/gcp-service-account.json
# gcloud 가 설정·로그를 쓸 곳. 홈 아래라 uid 1000 이 쓸 수 있다.
ENV CLOUDSDK_CONFIG=/home/pickage/.config/gcloud

# ENTRYPOINT 로 둔다 — `docker compose run --rm ingest-weekly --dry-run` 처럼 뒤에 붙인
# 인자가 그대로 넘어간다. `command:` 를 두면 기본 인자가 되어 이 형태를 가린다
# (ai-similarity 와 같은 이유).
ENTRYPOINT ["python", "-m", "pipeline.weekly.run"]
