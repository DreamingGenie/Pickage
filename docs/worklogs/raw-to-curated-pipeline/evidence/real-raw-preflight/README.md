# 서버 확인·입력 선정 결과

관측일: 2026-09-15. 입력 등록 확인: 17:17 KST. 후속 상태: **선정 입력 서버 등록 완료 / 실제 두 EC2 런타임·shuffle 검증 완료 / 실제 raw 성능 비교 대기**.

## 서버

| 항목 | data | app |
|---|---:|---:|
| 논리 CPU | 4 | 4 |
| RAM | 15.42 GiB | 15.42 GiB |
| 가용 RAM (16:50 KST) | 13.46 GiB | 13.59 GiB |
| 여유 디스크 | 260.30 GiB | 135.29 GiB |
| 관측 부하 | 낮음 | CI build 실행 중 |

첫 실험은 data에서 2 CPU / 총 6 GiB / 컨테이너 스왑 0 조건으로 시작할 계획이다. 작업 디스크 예산은 150 GiB. 전체 회차의 자원 적합성은 미측정이며 실험 직전 다시 확인한다. 기존 Spark worker 설정을 변경한 것은 아니다.

## 입력

| 용도 | 선택 | 위치 / 확인 |
|---|---|---|
| 주 스냅샷 | 2026-08-31 | 서버 MinIO |
| deps.dev 원본 run | bronze-20260907-v1 | versions_full / requirements / projects |
| 이전 Projects | 2026-08-24 | 서버 MinIO |
| 다운로드 run | downloads-278-20260909-v1 | 17:04 KST 서버 복사/검증 완료, 로컬 원본 보존 |
| 다운로드 계산 구간 | 2026-08-24 이상, 2026-08-31 미만 | 일별 7파일 / 14.62 MiB |
| dependents 대상 | 99,996개 이름 | 서버 등록 및 GET SHA/Parquet 검증 완료 |
| ID 부모 | null | 처음부터 전체 회차를 재구성하는 비교 |

선정 deps.dev 입력은 1,176개 객체 / 11.33 GiB, 다운로드 전체 run은 768개 객체 / 1.49 GiB다. 최소 계산 입력과 원본 run 전체 크기를 구분한다. 현재 서버에서 더 이른 package-version 부모는 발견되지 않았으며, 같은 날짜의 운영 `_current.json`은 바꾸지 않는다.

## 확인한 것과 아직 확인하지 않은 것

- 실제 manifest 바이트 SHA-256, 완료 marker 존재/형식, 생산자 검증 상태를 확인했다.
- raw/downloads manifest가 참조하는 모든 객체의 존재와 크기가 일치한다.
- 타깃 CSV는 직접 GET SHA 검증했고, 변환한 Parquet의 이름 수/유일성/스키마/해시를 확인했다.
- raw 전체를 다운로드하거나 모든 행을 읽지 않았다. 큰 파일 내용 SHA는 생산자 manifest에서 고정한 값이며, 실제 준비 다운로드 때 검증한다.
- 후속 다운로드 이전 작업에서는 다운로드 데이터 768개를 원본과 서버 양쪽에서 GET SHA-256 검증했다. 위 metadata-only 제한은 deps.dev 입력에 계속 적용된다.
- 서버 버킷 versioning은 Disabled다. manifest와 객체가 바뀌면 실행을 중단하도록 준비/측정 시 재확인해야 한다.
- 요청 JSON 구조 검증은 통과했지만, 서버 객체·실행 환경이 모두 준비됐다는 뜻은 아니다.

## 다음에 필요한 준비

1. 완료: 로컬 다운로드 원본 run을 manifest/marker를 유지한 채 서버로 복사하고 768개 데이터 파일의 SHA-256을 검증했다. 결과는 `downloads-transfer.json`, `downloads-server-verification.json`.
2. 완료: dependents 대상 Parquet를 `pickage-raw/experiments/raw-benchmark-20260915/targets/dependents-targets.parquet`에 등록했다. 99,996행/유일 이름 99,996개, 잘못된 이름 0개, SHA 일치. 보고서 `targets-registration.json`.
3. 실제 EC2 준비 완료: Spark 3.5.3 / Python 3.11 / Java 17 / Node 24 동일 이미지를 두 EC2의 별도 실험 worker에서 검증했다. 기존 배포와 worker는 변경하지 않았고 실험 컨테이너는 검증 후 정리했다.

사용자가 '기존 배포를 유지하고 서비스에 지장이 없도록 자원을 제한하며, 약간의 성능 영향은 허용'으로 조건을 명확히 했다. 서버 실행 전면 보류를 해제하고 실제 app/data 두 EC2에서 작은 분산 작업과 shuffle 검증을 완료했다. `input-selection.json`의 `ready_for_prepare` 및 `ready_for_benchmark`는 실제 입력 준비/측정 연결이 남아 있어 false다. `request.pending.json`은 자동 실행하지 않는다. 최신 결과는 `../../06-bounded-ec2-runtime.md`를 참조한다.

최초 사전 확인은 읽기 전용이었다. 이후 사용자 요청으로 다운로드 원본 run을 복사하고 고정 대상 Parquet를 서버 MinIO에 등록했다. 후속 두 EC2 smoke에서는 1만 정수를 계산했으며 실제 raw 전처리를 실행한 것은 아니다. 원천데이터 수집, 객체 삭제, DB 변경, Curated 포인터 갱신 및 실제 raw 성능 측정은 수행하지 않았다.
