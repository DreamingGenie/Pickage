# Pickage local MinIO

Docker Desktop의 Linux engine을 사용한다. 저장 데이터는 Docker named volume
`pickage-local_minio-data`에 유지된다. API/console은 localhost에만 공개한다.

## 실행

이 디렉터리의 `.env`에 `.env.example`의 변수와 별도 비밀번호를 설정한다.
`.env`는 Git에서 제외된다.

```powershell
docker compose -f docker-compose.local.yaml up -d
docker compose -f docker-compose.local.yaml ps -a
```

- Console: http://localhost:9001
- S3 API: http://localhost:9000
- 로그인: 로컬 `.env`의 값
- Bronze bucket: `pickage-raw`
- 나머지 버킷: `pickage-curated`, `pickage-vectors`,
  `pickage-mlflow-artifacts`, `pickage-quarantine`

프로젝트 루트의 `docker-compose.local.yaml`에서 로컬 서비스를 관리한다.
위 명령은 프로젝트 루트에서 실행한다.
MinIO가 healthy 상태가 되면 `minio-init`이 `init-buckets.sh`를 실행해
위 5개 버킷 중 없는 버킷만 생성한다. 기존 버킷과 객체는 유지한다.
일회성 서비스인 `minio-init`의 `Exited (0)` 상태는 초기화 성공을 뜻한다.
초기화 로그는 `docker compose -f docker-compose.local.yaml logs minio-init`으로 확인한다.
중지는 `docker compose -f docker-compose.local.yaml stop`으로 한다.
`down -v`는 저장 데이터를 삭제하므로 사용하지 않는다.
원본 Parquet는 별도 입고 작업으로 `pickage-raw`에 복사한다.
입고 실행: `.venv-bq/Scripts/python.exe pipeline/minio/ingest_raw.py --run-id bronze-20260907-v1 --workers 8`.
의존성 설치: `.venv-bq/Scripts/python.exe -m pip install -r pipeline/minio/requirements.txt`.
`--dry-run`으로 원본 manifest와 파일 수/크기/Parquet 행 수를 먼저 검증한다.
`--dataset projects --snapshot 2022-05-08`로 범위를 좁힐 수 있다.
대상은 `data/raw`의 deps.dev 데이터이며 다운로드 API 데이터는 포함하지 않는다.
목적지는 `pickage-raw/depsdev/v1/{table}/snapshot={date}/run_id={run}/data/`이다.
Projects는 여러 provider의 데이터이므로 `system=npm` prefix를 사용하지 않는다.
모든 업로드 객체는 GET으로 읽어 로컬 SHA-256과 비교한다.
원본 manifest를 보존하고 검증 결과 manifest 이후 `_SUCCESS`를 기록한다.
실패 시 같은 run ID로 재개하면 기존 파일은 해시 검증하고 빠진 파일만 전송한다.
기존 객체의 내용이 다르면 덮어쓰지 않고 실패한다. 같은 run은 동시에 실행하지 않는다.
Spark에는 여러 run의 glob 대신 정확한 승인 run 경로를 넘긴다.
이 구성은 로컬 단일 노드 개발용이며 서버 백업/권한 구성을 대신하지 않는다.
