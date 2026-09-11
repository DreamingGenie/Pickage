# 로컬 개발 환경

리포 루트에서 실행한다. compose 파일은 `compose.yaml` 하나다.

```bash
docker compose --profile api  up     # postgres + api
docker compose --profile data up     # minio + spark
docker compose --profile all  up     # 전부
```

DB 는 뜨자마자 스키마가 잡히지만 **테이블은 비어 있다.** 샘플 데이터가 필요하면
아래 "샘플 데이터 넣기" 의 명령을 한 번 돌린다.

매번 `--profile` 붙이기 번거로우면 `cp .env.example .env` 후 작업에 맞는 프로파일을 적어 두면
`docker compose up` 만으로 뜬다. (`.env` 는 커밋되지 않으므로 각자 취향대로 두면 된다)

## 데이터 파트는 첫 실행 전 준비가 하나 있다

MinIO 자격증명은 커밋하지 않는다. 각자 만든다.

```bash
cp pipeline/minio/.env.example pipeline/minio/.env
# MINIO_ROOT_PASSWORD 를 임의 값으로 채운다
```

## 접속 정보

Postgres·API 값은 로컬 전용이라 커밋되어 있다. **운영 서버 자격증명과 절대 같게 두지 말 것.**
전부 `127.0.0.1` 에만 열려 있어 같은 네트워크의 다른 사람은 접근할 수 없다.

| | 주소 | 계정 |
| --- | --- | --- |
| API | http://localhost:8080/swagger-ui/index.html | |
| Postgres | `localhost:15432` | `postgres` / `pickage` |
| MinIO | `http://localhost:9000` | `pipeline/minio/.env` 의 값 |
| MinIO 콘솔 | http://localhost:9001 | 위와 같음 |

> **서버 MinIO 에 넣으려는 것이면 이 문서가 아니다.** 서버는 외부 포트가 없어 SSH 터널로
> 붙고, 자격증명 파일도 따로 쓴다. 절차는
> [pipeline/minio/README.md](../../pipeline/minio/README.md) 의 "서버 MinIO 로 적재하기".
>
> 터널의 **내 PC 쪽 입구를 19000** 으로 낸다(서버는 9000 그대로다). 입구를 9000 으로
> 잡으면 아래 로컬 MinIO 와 같은 주소가 되어, 터널을 잊었을 때 서버로 갈 데이터가
> **오류 없이 로컬로 들어간다.**

버킷 5종은 `minio-init` 이 기동 시 **없는 것만** 만든다. 기존 버킷과 객체는 유지된다.
`minio-init` 이 `Exited (0)` 인 것은 초기화 성공을 뜻한다.

`pickage-raw` · `pickage-curated` · `pickage-vectors` · `pickage-mlflow-artifacts` · `pickage-quarantine`

버킷별 역할은 [pipeline/minio/README.md](../../pipeline/minio/README.md) 참고.

## ⚠ 초기화 — `down -v` 를 쓰지 말 것

`docker compose down -v` 는 **MinIO 에 적재한 원본까지 지운다.** 재수집에 로컬 원본 수십 GB 가 필요하다.

```bash
docker compose --profile all down       # 내린다. 데이터는 남는다
docker compose --profile all stop       # 컨테이너만 멈춘다
```

DB 만 초기화해야 하면 볼륨을 지정해서 지운다.

```bash
docker compose --profile api down
docker volume rm pickage-local_pgdata
```

> 스키마 변경은 대부분 이게 필요 없다. 마이그레이션이 자동으로 맞춰 준다.

## 스키마와 샘플 데이터

두 개는 성격이 다르다. **스키마는 앱이 자동으로, 샘플 데이터는 사람이 명령으로** 넣는다.

| | 파일 | 누가 적용하나 |
| --- | --- | --- |
| 스키마 | `backend/src/main/resources/db/migration/` 의 `V1__init.sql` · `V2__add_curated_load_execution.sql` · `V3__add_snapshot_reference_execution.sql` · `V4__index_similar_package.sql` | 앱이 뜰 때 Flyway 가 자동 |
| 샘플 데이터 | `deploy/local/seed/*.sql` | **아래 명령으로 직접** |

**테이블은 손으로 만들지 않는다.** 로컬과 운영이 같은 마이그레이션 파일을 쓰므로 스키마가 갈라질 수 없다.

### 샘플 데이터 — 목적이 다른 세 벌

**아래 셋을 같이 쓸 수 없다.** 전부 기존 행을 비우고 시작하므로 나중에 돌린 쪽만 남는다.
(그 아래 두 개는 데이터를 넣지 않는 **비우기 전용**이라 셋 중 무엇 위에도 얹을 수 있다.)

| 파일 | 규모 | 무엇을 보려고 |
| --- | --- | --- |
| `seed_sample.sql` | 패키지 3 × 스냅샷 2 | **자료가 모자란 상태.** 추이 그래프가 "데이터 축적 중" 으로 뜨는지, `repo_url` 이 없는 패키지가 "미확인" 으로 뜨는지 |
| `seed_mock_parity.sql` | 패키지 369 × 스냅샷 130 | **mock 과 같은 숫자.** `VITE_USE_MOCK=true` 인 화면과 번갈아 보며 다른 곳을 찾는 대조 검증 |
| `seed_service_full.sql` | 패키지 322 × 스냅샷 130 | **목업을 굴려 보는 상태.** 메인 6개 테이블을 전부 채우고(`similar_package` 포함) 경계 사례를 일부러 심어 두었다 |
| `seed_clear_snapshots.sql` | 넣지 않음 | **자료가 아예 없는 상태.** 위 시드 뒤에 얹으면 이름은 남고 스냅샷만 사라진다. 적재 전·첫 스냅샷 대기 중의 정상 상태이며, 이때 5개 엔드포인트가 전부 200 이어야 한다 (S15P21A506-298) |
| `seed_reset.sql` | 넣지 않음 | **목업을 실데이터로 교체하기 직전 1회.** 6개 테이블을 전부 비운다. 아래 "목업에서 실데이터로" 참고 |

`seed_mock_parity` 와 `seed_service_full` 은 규모가 비슷하지만 쓰임이 다르다. 앞은 **mock 과
숫자가 같아야** 의미가 있어서 값을 바꾸려면 `frontend/src/api/mock/dataset.ts` 부터 고쳐야
하고, 뒤는 **화면이 깨지는 데이터를 일부러 담는 쪽**이라 시드 파일만 고치면 된다
(deprecated·NULL 지표·신규 패키지·스냅샷 없는 패키지·스코프 이름 등 — 목록은 파일 머리말).

```bash
docker compose exec postgres psql -U postgres -d pickage -f seed/seed_sample.sql
docker compose exec postgres psql -U postgres -d pickage -f seed/seed_mock_parity.sql
docker compose exec postgres psql -U postgres -d pickage -f seed/seed_service_full.sql
docker compose exec postgres psql -U postgres -d pickage -f seed/seed_clear_snapshots.sql
```

### 목업에서 실데이터로

실적재기(`pipeline/postgresql`)는 전량 교체가 아니라 임시 staging + upsert 라 **목업 행을
스스로 걷어내지 않는다.** 그래서 정제 데이터를 처음 적재하기 직전에 `seed_reset.sql` 을
한 번 돌린다.

잊고 적재하면 **조용히 섞이지 않는다.** 적재기가 게시 직전에 `package_id` ↔ `name` 짝을
검사해 `package_id/name collision` 으로 예외를 던지고 트랜잭션을 통째로 롤백한다. 목업은
`package_id` 를 1 부터 제 순서대로 배정하므로 거의 확실히 걸린다 — 그 메시지를 보면 여기로
올 것.

반대 방향은 막혀 있다. 실적재가 한 번 성공하면 `etl_snapshot_reference` 에 이력이 남고,
그 뒤로는 모든 시드의 `DELETE FROM snapshot` 이 FK 위반으로 멈춘다.

> 시드는 **메인 서비스 6개 테이블만** 건드린다. 적재 추적(`etl_*`) 4개는 파이프라인이
> 소유하므로 비우지도 채우지도 않는다. 그래서 `snapshot` 은 `TRUNCATE` 가 아니라 `DELETE`
> 다 — 적재 이력이 있는 DB 에서는 FK 위반으로 **멈춘다.** 조용히 덮어쓰지 않는 쪽이 맞다.

이 명령은 샘플 DB를 재설정할 때만 사용한다. `TRUNCATE` 후 샘플 행을 다시 넣으므로,
값을 고치고 다시 실행하면 기존 샘플 데이터가 교체된다.

> ⚠ 실제 Curated 적재 DB에서 이 명령을 실행하거나 `TRUNCATE`로 데이터를 비우지 말 것.
> `package`, `version` 및 실행 이력은 PostgreSQL 적재기가 소유한다. 적재 실패 복구에는
> seed를 사용하지 않는다.

숫자는 전부 지어낸 값이다. 형태만 맞춰 둔 것이므로 분석 근거로 쓰지 말 것.

**경로 앞에 `/` 를 붙이지 말 것.** Git Bash 가 `/seed/...` 를 윈도우 경로로 바꿔서
`No such file or directory` 가 난다. 컨테이너의 작업 디렉터리가 `/` 라서 상대 경로로도
같은 파일을 가리키고, 이렇게 쓰면 PowerShell 과 Git Bash 에서 같은 명령이 통한다.

<details>
<summary>왜 앱이 자동으로 넣지 않나</summary>

Flyway 의 반복 마이그레이션(`R__`)으로 두면 파일이 바뀔 때마다 앱이 알아서 다시 넣는다.
편하지만 **남이 시드를 고쳐 push 한 것을 내가 pull 한 순간, 내 로컬 데이터가 말없이 사라진다.**
시드 파일을 건드린 적도 없는 사람에게 그 일이 생긴다. 지우는 시점은 사람이 정해야 한다.

곁따라오는 이득도 있다.

- 시드 파일이 `resources` 밖에 있어 **jar 에 실리지 않는다.** 운영에 들어갈 경로가 아예 없다 —
  Flyway 설정에 의존해서 막는 것보다 확실하다.
- 체크섬·적용 이력이 없어서 "시드를 고쳤는데 기동이 막힌다" 류의 함정이 생기지 않는다.

</details>

### mock 을 끄고 화면까지 확인하기

프런트는 기본이 mock 이다. **서버를 거치는지 보려면 꺼야 한다** — 켜 두면 화면이 예쁘게
떠도 그것은 `src/api/mock` 이 만든 값이다.

```bash
printf 'VITE_API_BASE_URL=/api\nVITE_USE_MOCK=false\n' > frontend/.env.local
```

`.env.local` 은 `.gitignore` 에 걸려 있어 커밋되지 않는다. **값을 바꾸면 dev 서버를 다시
띄운다** — Vite 는 기동 시점에 이 파일을 읽는다.

그다음 셋을 순서대로 올린다.

```bash
docker compose --profile api up -d postgres
docker compose exec -T postgres psql -U postgres -d pickage -f seed/seed_service_full.sql
cd backend && ./gradlew bootRun          # 8080
cd frontend && npm run dev               # 5173, /api 는 8080 으로 프록시된다
```

`http://localhost:5173/report/draft` 로 바로 들어가면 기본 조합(winston·pino·bunyan)으로
생태계 탭이 뜬다. **화면-01·02 를 거칠 필요가 없다** — 그쪽은 아직
`routes/analyze/sample-registry.ts` 하드코딩이라 서버를 타지 않는다(S15P21A506-120).

시드를 갈아 끼우면 같은 화면에서 상태 네 가지를 다 볼 수 있다.

| 시드 | 화면에 떠야 하는 것 |
| --- | --- |
| `seed_service_full` | 차트 두 개에 104주치 선 3개, 카드 3장 |
| `seed_sample` | 기본 조합 이름이 하나도 없어 **"찾지 못한 패키지: …"** 만 뜬다. 500 이 아니다 |
| `seed_sample` + 화면-01 에서 `lodash` | **"데이터 축적 중 · 2주차"** — 점이 3개 미만이면 선을 그리지 않는다 |
| `seed_clear_snapshots` | **"기준 스냅샷 없음 — 데이터 축적 중"** (S15P21A506-298) |

`/api/dict-manifest` 는 아직 404 다(S15P21A506-291). **그래도 검색창은 동작해야 한다** —
사전은 최적화이지 의존성이 아니라서, 실패하면 전량 `/api/packages/search` 폴백으로 돈다.
개발자 도구 네트워크 탭에서 404 하나와 그 뒤의 `search` 200 이 같이 보이면 정상이다.

> 보고서를 한 번 열 때 나가는 요청은 **4개**다(개요 1 + 추이 2 + 버전 분포 1).
> 그보다 많으면 기준일이 오기 전에 추이가 먼저 나간 것이다 — 예전에 7개였고
> 세 개는 화면에 뜨지도 못한 채 버려졌다(S15P21A506-303).

## Curated package·version 적재

Curated의 승인된 `package-version` 실행을 PostgreSQL에 넣을 때는
[pipeline/postgresql/README.md](../../pipeline/postgresql/README.md)의 loader를 사용한다.
일반 사용자 DB의 V1·V2 스키마는 앱이 Flyway로 적용한다. SQL 파일을 직접 붙여 넣어
마이그레이션을 우회하지 않는다.

적재 전에는 다음 조건을 확인한다.

- MinIO의 `pickage-curated`에 `_SUCCESS`와 `run_manifest.json`이 있는 승인 Curated run이다.
- `pipeline/minio/.env`가 준비되어 있고, 입력 파일을 받을 로컬 디스크 공간이 충분하다.
- DB가 앱이 사용하는 PostgreSQL 16 스키마를 Flyway로 적용한 상태다.
- 실행 ID와 snapshot을 명시하고, 비밀번호는 CLI·리포트·로그에 넣지 않는다.

입력을 DB 없이 먼저 확인하려면 loader의 `--verify-only`를 사용한다.

```powershell
.venv-bq\Scripts\python.exe -m pipeline.postgresql.load `
  --snapshot 2026-08-31 `
  --curated-run-id curated-20260907-v2 `
  --execution-id verify-20260907-v2 `
  --verify-only
```

실제 적재는 Docker 컨테이너의 `psql` 또는 호스트 `psql`을 명시한다. 연결 방법, 재실행,
실패한 PREPARING 세션 복구, commit 응답 유실 확인은 위 적재 안내를 기준으로 한다.

`pipeline/postgresql/test_integration.py`가 V1·V2를 직접 적용하는 것은 격리된 테스트 DB를
만드는 테스트 harness에 한정된다. 이 테스트는 `pickage` 애플리케이션 DB와 seed를 사용하지
않는다.

### 스키마를 바꿀 때

**이미 적용된 `V__` 파일은 고치지 않는다.** 변경은 새 파일로만 한다.

```
V1__init.sql          ← 고치지 말 것
V2__add_owner.sql     ← 새로 만든다
```

Flyway 는 적용한 파일의 체크섬을 `flyway_schema_history` 에 적어 두고 기동할 때마다 대조한다.
고치면 어긋나서 **기동이 실패한다. 로컬도 예외가 아니다.**

실패 메시지에 안내가 함께 나온다. 둘 중 하나를 고르면 된다.

**1) 파일을 되돌리고 변경을 새 `V__` 로 만든다** — 팀에 이미 공유된 마이그레이션이면 이쪽이다.

**2) 로컬 DB 를 버리고 처음부터 다시 적용한다** — 아직 나만 가진 변경이면 이쪽이다.

```bash
docker compose --profile api down
docker volume rm pickage-local_pgdata
```

이 볼륨 삭제는 해당 로컬 PostgreSQL의 모든 데이터와 적재 이력을 폐기한다. 샘플 DB를
처음부터 다시 만들 때만 사용하고, Curated 적재 결과를 복구하는 방법으로 사용하지 않는다.
삭제 전에 `docker volume ls`로 정확한 볼륨 이름을 확인한다.

> **앱이 DB 를 대신 비워 주지는 않는다.** 검증 실패를 잡아 `clean` 후 재적용하게 만들 수도
> 있지만, 그건 로컬 DB 의 데이터를 조용히 지우는 경로가 된다. 시드만 있을 때는 손해가 없어
> 위험이 드러나지 않고, 직접 넣은 데이터나 적재한 수집 결과가 있을 때 처음 드러난다.
> `spring.flyway.clean-disabled` 를 기본값(비활성)으로 두었으므로 그 경로는 아예 없다.

### 엔티티는 테이블을 따라간다

`spring.jpa.hibernate.ddl-auto: validate` 라서, 엔티티와 실제 테이블이 다르면
**기동이 실패한다.** 컬럼을 추가하려면 `V__` 마이그레이션을 먼저 쓰고 엔티티를 맞춘다.

**아직 엔티티가 없어서 지금은 검사할 대상도 없다.** 첫 엔티티가 생기는 순간부터 걸린다.

`update` 로 바꾸지 말 것. Hibernate 가 테이블을 말없이 고쳐서 로컬 스키마가 마이그레이션과
갈라지고, 그 사실은 서버에 올린 뒤에야 드러난다.

## Spark

```bash
docker compose exec spark pyspark
docker compose exec spark spark-submit /opt/work/작업파일.py
```

`pipeline/` 이 컨테이너의 `/opt/work` 로 마운트된다. 호스트에서 고치면 바로 반영된다.

**s3a 설정과 자격증명은 이미 되어 있다.** 코드에 config 를 쓰지 않아도 된다.

```python
spark = SparkSession.builder.master("local[*]").getOrCreate()
spark.read.parquet("s3a://pickage-raw/...")
```

자격증명은 `pipeline/minio/.env` 를 그대로 물려받는다. `spark-env.sh` 가 `MINIO_ROOT_*` 을
s3a 가 읽는 `AWS_*` 이름으로 바꿔 주므로 `.env` 에 같은 값을 두 번 적지 않아도 된다.

## 지켜야 할 것 두 가지

**1. 경로는 `key=value/` 로 쓴다.**

```
s3a://pickage-raw/npm/downloads/collected_date=2026-09-07/
```

이렇게 쓰면 Spark 가 `collected_date` 를 컬럼으로 자동 인식한다.
그냥 `2026-09-07/` 로 쓰면 파일명을 파싱하는 코드를 매번 써야 하고 파티션 프루닝도 안 된다.

**2. 버킷 이름에 언더스코어를 쓰지 않는다.** `pkg_vectors`(X) → `pickage-vectors`(O)

s3a 와 일부 SDK 가 거부한다. 데이터가 들어간 뒤에는 이름을 못 바꿔 전부 복사해야 한다.

## boto3

```python
s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id=os.environ["MINIO_ROOT_USER"],
    aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
    config=boto3.session.Config(s3={"addressing_style": "path"}),   # 필수
)
```

`addressing_style="path"` 가 없으면 연결되지 않는다. 기본값은 `http://버킷명.endpoint/`
형태로 붙는데 MinIO 는 그 주소로 응답하지 않는다. Spark 의 `path.style.access=true` 와 같은 이유다.

## 막히면

| 증상 | 원인 |
| --- | --- |
| `Cannot connect to the Docker daemon` | Docker Desktop 이 꺼져 있다. `docker info` 로 확인 (`docker --version` 은 데몬이 죽어도 답한다) |
| `up` 했는데 아무것도 안 뜸 | `--profile` 을 빠뜨렸다 |
| `env file ... not found` | `pipeline/minio/.env` 가 없다. 위 "첫 실행 전 준비" 참고 |
| `Port 8080 already in use` 인데 브라우저는 뜸 | 이전 앱 프로세스가 남아 있다. `netstat -ano \| findstr :8080` |
| `NoSuchMethodError` (Spark) | `hadoop-aws` 버전 불일치 (아래) |
| MinIO 연결 실패 | `path.style.access` / `addressing_style` 누락 |
| s3a 에서 403 · `AccessDenied` | `pipeline/minio/.env` 를 바꾼 뒤 spark 컨테이너를 재기동하지 않았다 |
| 셸 스크립트가 컨테이너에서 깨짐 | CRLF. 루트 `.gitattributes` 가 막아 주지만, 이미 받은 파일은 다시 체크아웃해야 한다 |
| `.env` 를 고쳤는데 안 먹음 | **셸 환경변수가 `.env` 보다 우선한다.** `echo $COMPOSE_PROFILES` 로 확인 |
| `.env` 에 키를 넣었는데 앱이 못 읽음 | 루트 `.env` 는 compose 파일 해석에만 쓰인다. 컨테이너로 넘기려면 `env_file:` 또는 `environment:` 가 필요하다 |
| PowerShell 에서 `curl` 이 이상함 | PowerShell 의 `curl` 은 `Invoke-WebRequest` 별칭이다. `curl.exe` 를 쓰거나 Git Bash |
| Git Bash 에서 `/opt/...` 가 `C:\...` 로 바뀜 | `MSYS_NO_PATHCONV=1` 을 앞에 붙인다 |
| 기동 실패 — `Validate failed ... checksum mismatch` | 적용된 `V__` 파일을 고쳤다. **정상 동작이다** — 로그의 안내 두 갈래 중 하나를 고를 것 (위 "스키마를 바꿀 때") |
| 기동 실패 — `SchemaManagementException` / `missing column` | 엔티티와 테이블 불일치. **정상 동작이다** — `V__` 마이그레이션을 먼저 쓸 것 |
| 시드를 고쳤는데 반영 안 됨 | 시드는 앱이 넣지 않는다. `psql -f seed/seed_sample.sql` 을 다시 돌릴 것 (위 "샘플 데이터 넣기") |

## 버전을 고정한 이유

올리기 전에 읽을 것.

| 대상 | 버전 | 이유 |
| --- | --- | --- |
| `apache/spark` | `3.5.3-python3` | 내장 Hadoop 이 3.3.4 |
| `hadoop-aws` | `3.3.4` | **Spark 내장 Hadoop 과 정확히 같아야 한다.** 어긋나면 `NoSuchMethodError` 로 죽고 원인이 드러나지 않는다 |
| `minio/minio` | 다이제스트 고정 | 태그는 같은 이름으로 재발행될 수 있다 |
| `postgres` | `16` | 운영 서버와 같은 메이저 버전 |

Spark 를 올리면 `hadoop-aws` 도 같이 맞춘다. 내장 버전 확인:

```bash
docker run --rm apache/spark:<태그> ls /opt/spark/jars | grep hadoop-client-api
```

설정 파일은 `deploy/local/spark/` 아래에 있다.

## 프로젝트 이름

컨테이너·볼륨 이름의 접두사다.

| 환경 | 이름 | 예 |
| --- | --- | --- |
| 로컬 | `pickage-local` | `pickage-local-api-1`, `pickage-local_minio-data` |
| 운영 | `pickage-prod` | `pickage-prod-api-1` |

이름이 환경을 드러내므로, 운영 compose 를 실수로 로컬에서 띄우면 `docker ps` 에서 바로 보인다.

**이 이름을 바꾸면 볼륨 이름도 같이 바뀌어 기존 데이터가 고아 볼륨으로 남는다.**
증상이 "컨테이너는 정상인데 데이터만 없음" 으로 나타나 원인 찾기 어렵다.
