# 실제 raw 데이터 Spark 비교 작업 로그

## 변경 범위

2026-09-15: 실험 계획 작성. 실제 데이터 비교를 위한 입력 고정, 서버 자원 확인, 측정 보강, 단일/두 노드 비교 및 판단 기준을 정리했다. 구현·서버 실행은 아직 하지 않았다.

## 작업 계획

상세 계획: `.omx/plans/real-raw-spark-benchmark.md`.

1. 서버 현황과 완료된 raw 입력 계약 확인.
2. 컨테이너 전체 CPU/메모리 및 Spark 지표 측정 보강, 합성 스모크.
3. 실제 입력 준비와 동일 자원 단일 노드 비교.
4. 동등성 통과 후 두 노드 비교.
5. 결과 보고와 전처리 방식 선택 제안.

## 실제 진행한 작업

- 실험 워크트리의 `codex/raw-to-curated-pipeline`, HEAD `878a0c0` 확인.
- 기존 README 및 prepare/benchmark/job 구현과 현재 원본 폴더의 운영 배포 문서를 확인.
- 기존 방식에도 local Spark가 포함되고, prepare가 기준 계산까지 실행하며, 현재 비교가 고정 단계 입력 방식임을 계획에 반영.
- 실험 런타임 3.5.7과 운영 설정 3.5.3 차이, driver를 포함한 worker1 메모리 상한, app의 서비스 공존을 기록.
- 원본 폴더는 현재 `infra/config/S15P21A506-223-cd-pipeline`, HEAD `194154a`로 확인했으며 변경하지 않음.

## 이슈와 해결 방향

- CPU/메모리 필드가 미측정: 실제 데이터 실행 전에 측정 보강 예정.
- 두 노드 런처는 Spark 제출 준비만 지원: 결과 회수/동등성 대조와 총 자원 집계를 실행 계획에 추가.
- 서버 DB 적재 종료는 사용자 확인 사항. 현재 서버 부하와 사용 가능한 자원은 실행 전 확인 예정.

## 결과와 미실행 사항

계획 문서만 작성했다. 실제 raw 회차 미선정, 서버 접속/부하 확인 미실행, 측정 기능 미구현, 실제 성능 비교 미실행. 운영 MinIO 게시/DB 변경 없음. Jira 연결 보류는 이전 사용자 결정을 유지한다.

## 1번 실행 결과 — 2026-09-15 16:45~16:54 KST

위 미실행 상태는 계획 작성 시점의 기록이다. 사용자 요청으로 서버 확인과 입력 선정을 진행했다.

### 실제 진행한 작업

- 기존 SSH 개인키를 인증에만 사용해 app/data 호스트의 CPU, RAM, 디스크, 컨테이너 상태/상한, Spark 런타임 및 master 등록 상태를 읽었다. 키·자격증명은 결과에 포함하지 않았다.
- data: 4 CPU, RAM 15.42 GiB, 가용 RAM 13.46 GiB, 여유 디스크 260.30 GiB. app: 4 CPU, RAM 15.42 GiB, 가용 RAM 13.59 GiB, 여유 디스크 135.29 GiB. 16:50 KST 시점 값이며 예약량이 아니다.
- app에서 GitLab CI build 실행을 관측했다. data master에는 worker 둘이 ALIVE, 실행 중 Spark application/driver는 0이었다. 광고 자원은 data 3 cores/8 GiB, app 2 cores/5 GiB다.
- 첫 단일 노드 실험 장소를 data로 선정했다. 시작 프로필은 2 CPU, 컨테이너 총 6 GiB/스왑 0, 엔진 메모리 2GB, 실험 작업 디스크 예산 150 GiB다. 준비/전체 회차가 실제로 이 상한에 들어가는지는 아직 검증하지 않았으며 실행 직전에 가용량을 다시 확인한다.
- 서버 `pickage-raw`를 조회해 2026-08-31의 versions_full, requirements, projects 및 직전 2026-08-24 projects를 선정했다. 원본 run은 `bronze-20260907-v1`. 총 1,176개 데이터 객체, 12,167,181,812 bytes(11.33 GiB)다.
- 선택한 raw의 PASSED/GET_SHA256_ALL_FILES manifest와 `_SUCCESS`, `source_manifest.json`을 읽고 manifest의 실제 SHA-256을 기록했다. 참조 객체 모두 목록에 있고 크기도 일치했다. 전체 Parquet의 GET SHA/행 검증을 다시 실행한 것은 아니다.
- 서버 MinIO에는 `npm-downloads/v1/` 데이터가 없다. 로컬 MinIO에서 `downloads-278-20260909-v1`를 발견하고 manifest SHA `0617c12a1c810ecc11fcc01e281e375a8c1aa53bdb5ba57dab15a61120eec35d`, `_INPUT`/`_SUCCESS`, consistency checks 및 768개 객체의 존재/크기를 확인했다.
- 다운로드 전체 run은 1.49 GiB, 2024-09-01~2026-08-31 자료다. 실험 집계 구간은 `[2026-08-24, 2026-08-31)`이며 해당 7일 parquet 합계 14.62 MiB다. 전체 raw run 이전량과 계산에 쓰는 일별 데이터량을 구분한다. 선언된 READY 99,215개와 NOT_FOUND 781개를 유지하며 품질 예외를 제거하지 않는다.
- 위 다운로드 run의 target CSV를 SHA 검증 후 로컬에 받아 name 한 열의 distinct Parquet를 만들었다. 100,000행 중 동일 이름 중복 4행을 합쳐 99,996개의 고유 이름을 고정했다. NULL/빈 이름/공백 보정은 없으며 정확히 `name VARCHAR` 한 열, 고유 이름 99,996개, 잘못된 이름 0개를 확인했다. 파일 SHA는 `ccc05cbdd12c1639a41d3fa3cc1757101b2c1b786b926e18f0028985c6dcc468`.
- 서버에서 발견한 package-version parent는 같은 날짜의 `curated-20260907-v2`뿐이었다. 첫 비교 시나리오는 `parent:null`인 전체 스냅샷 재구성으로 명시하고 현재 포인터는 참고 기록으로 고정했다. 이후 신규 스냅샷 ID 증가 성능을 측정했다고 주장하지 않는다.
- 두 worker의 실제 런타임은 Spark 3.5.3 / Python 3.8.10 / Java 11이며 Node가 없다. 실험 이미지의 Python 3.11 / Java 17 / Node 환경과 다르므로 기존 worker에 그대로 제출할 수 없다.

### 산출물과 검증

요약: [입력 선정 보고서](evidence/real-raw-preflight/README.md).

- `evidence/real-raw-preflight/app-host.json`, `data-host.json`, `spark-cluster.json`: 관측한 자원과 Spark 상태.
- `server-storage.json`, `local-storage.json`: 객체 목록·크기·ETag와 원문 metadata/실제 manifest SHA. ETag를 SHA-256으로 취급하지 않았다.
- `input-selection.json`: 선정 결과, 비교 자원, 검증 수준과 장애 조건.
- `targets-selection.json`: 타깃 원본·변환 규칙·스키마·개수·해시. 생성 데이터는 Git 제외 경로 `data/spark-experiment/preflight-20260915/`에 보존한다.
- `request.pending.json`: 구조 검증 PASS. 다운로드/타깃이 서버에 없으므로 실행 준비 완료를 뜻하지 않는다. timestamp는 기존 source-linked Curated 보고서에서 얻었으며 raw Projects의 실제 timestamp 교차 검증은 prepare 단계에서 한다.
- `inspect_host.py`, `inspect_storage.py`: 읽기 전용 재확인 스크립트.

### 남은 사항 / 완료 범위

서버 조사와 입력 후보 선정은 완료했다. **서버에 전체 실험 입력이 갖춰진 상태는 아니다** (`ready_for_prepare=false`, `ready_for_benchmark=false`). 다운로드 불변 run의 서버 이전, 타깃 Parquet의 서버 등록, 격리된 호환 실행 환경 준비가 남았다. 다운로드를 다른 데이터로 대체하거나 없는 경로를 준비 완료로 기록하지 않았다.

서버에서는 조회만 수행했고 원본 MinIO/DB/서비스 설정을 변경하지 않았다. 실제 prepare, 전처리, 성능 측정, DB 적재는 실행하지 않았다. 이번 조회용 로컬 보고서와 이름 목록만 생성했다.

## 다운로드 원본 run 서버 복사 — 착수

사용자가 다운로드 원천데이터의 서버 MinIO 이전을 요청했다. 범위는 `pickage-raw/npm-downloads/v1/run_id=downloads-278-20260909-v1/` 한 run의 동일 바이트 복사와 무결성 검증이다. 소스 삭제, Curated 변경, DB 변경, 별도 dependents 대상 업로드는 포함하지 않는다.

- 사전 확인: 소스 771객체(데이터 768개와 제어 파일 3개), 서버 같은 prefix는 0객체. 데이터 합계 1,597,476,963 bytes, 제어 파일 포함 1,598,541,546 bytes. manifest SHA는 기존에 고정한 `0617c12a1c810ecc11fcc01e281e375a8c1aa53bdb5ba57dab15a61120eec35d`와 일치한다.
- SSH 터널로 서버에 연결하며 자격증명은 기존 로컬 파일에서 메모리로만 읽는다.
- 먼저 로컬 소스의 768개 파일을 GET SHA-256 검증해 격리 캐시에 고정한다. 기존 `pipeline.downloads.bronze.publish`를 재사용해 조건부 생성하고 서버 GET SHA-256으로 전량 검증한 뒤 원본 manifest와 `_SUCCESS`를 마지막에 게시한다.
- 원본 manifest를 재생성하거나 현재 코드 해시로 바꾸지 않는다. 기존 publisher의 canonical bytes가 원본과 동일한지 실행 전에 강제 확인한다.
- publisher 회귀 테스트 8개 통과. 실행 스크립트 문법 및 작업 루트 확인 통과. 결과는 `evidence/real-raw-preflight/downloads-transfer.json`에 남긴다.

### 복사·검증 완료 — 2026-09-15 17:04 KST

- 실행 16:59:32~17:03:36 KST, 소요 244.094초(약 4분 4초). 실패 없이 `VERIFIED`로 완료했다.
- 서버 경로: `s3://pickage-raw/npm-downloads/v1/run_id=downloads-278-20260909-v1/`.
- 768개 데이터 파일을 원본에서 GET SHA-256 검증한 뒤 서버로 복사했고 서버에서도 768개 전부 GET SHA-256을 검증했다. `_INPUT.json`, `run_manifest.json`, `_SUCCESS`의 바이트도 원본과 동일하다.
- 최종 771객체 / 1,598,541,546 bytes이며 manifest SHA는 `0617c12a1c810ecc11fcc01e281e375a8c1aa53bdb5ba57dab15a61120eec35d` 그대로다. `_SUCCESS`는 전량 검증 후 마지막에 기록했다.
- 17:04 KST 서버 자체에서 별도로 S3 API를 호출해 manifest SHA, 완료 marker, 전체 객체 목록/크기를 재확인했고 PASS였다. 중복된 전체 GET 검증은 하지 않았다.
- 증거: `downloads-transfer.json`(전량 해시 검증), `downloads-server-verification.json`(독립 서버 확인). `input-selection.json`의 다운로드 위치/검증 상태와 해결된 장애 조건을 갱신했다.
- 로컬 MinIO 원본과 이번 검증 캐시는 보존했다. 사용한 작업 전용 SSH 터널만 종료했다. DB, Curated, dependents 전용 타깃 등록, 런타임 변경은 수행하지 않았다.
- 남은 실험 준비는 name-only 타깃의 서버 등록과 호환 실행 환경 구성이다. 따라서 `ready_for_prepare=false`, `ready_for_benchmark=false`를 유지한다.

## 고정 패키지 대상 목록 등록 — 착수

사용자가 고정 목록의 서버 등록을 승인했다. `pickage-raw/experiments/raw-benchmark-20260915/targets/dependents-targets.parquet` 한 객체를 등록한다. 로컬에 고정한 99,996개 이름 / 1,080,529 bytes / SHA `ccc05cbdd12c1639a41d3fa3cc1757101b2c1b786b926e18f0028985c6dcc468`을 기준으로 한다.

먼저 로컬 파일과 요청의 참조를 검증하고, 기존 immutable PUT helper로 기존 객체가 없을 때만 생성한다. 서버에서 파일 전체를 다시 읽어 해시·스키마·행 수·유일성·잘못된 이름 여부를 검증한다. 등록 결과만 갱신하고 전처리나 런타임 변경은 실행하지 않는다.

### 등록 완료 — 2026-09-15 17:17 KST

- 대상 객체가 없어 조건부 PUT(`IfNoneMatch=*`)으로 신규 생성했다. 기존의 다른 바이트를 덮어쓰는 경로는 사용하지 않았다.
- 서버 객체 전체를 GET한 결과 1,080,529 bytes, SHA `ccc05cbdd12c1639a41d3fa3cc1757101b2c1b786b926e18f0028985c6dcc468`으로 원본과 정확히 일치했다.
- 서버에서 받은 바이트를 Parquet로 열어 `name VARCHAR` 한 열, 99,996행, 고유 이름 99,996개, NULL/빈 이름/앞뒤 공백/NUL 이름 0개를 확인했다.
- `request.pending.json`의 `targets.dependents` 버킷·경로·SHA가 등록 객체와 일치하고 요청 구조 검증이 통과했다. 이미 같은 값으로 고정되어 있으므로 요청 본문을 바꾸지 않았다.
- `targets-registration.json`은 `VERIFIED` / `CREATED`. `targets-selection.json`의 `server_uploaded=true` 및 서버 참조를 기록하고 `input-selection.json`에서 타깃 미등록 장애 조건을 제거했다.
- 초기 입력은 서버에 준비됐지만 실험 런타임 준비는 남아 있어 `ready_for_prepare=false`, `ready_for_benchmark=false`를 유지한다. 실제 prepare/측정/DB 작업은 시작하지 않았다.
- 등록 후 작업 전용 SSH 터널을 종료했다. 재실행 가능한 등록 스크립트 `register_targets.py`와 검증 보고서를 보존했다.
