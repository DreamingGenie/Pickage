# 실제 전체 입력 실패 수정 및 재실행

## 변경 범위·계획

- repository 입력의 불필요한 전체 컬럼 materialization을 제거하고 회귀 테스트로 출력 계약을 확인한다.
- 임시 디스크 한도 10GB 고정을 실행 옵션으로 바꾸고 여유 공간 검사 및 사용량 기록을 추가한다.
- hydration은 검증된 기존 파일을 재사용하고 immutable cache 사본은 hardlink를 우선 사용한다.
- 승인된 Curated 산출물은 남기고, 닫힌 작업 DB와 중복 캐시만 정리한다.
- 기존 C:/pg914의 실패 기록·원래 코드 및 MinIO 산출물은 보존한다. C:/pg914r2에서
  새 실행 ID 및 별도 MinIO를 사용한다. 기존 생성 계약 해시를 변경해 재사용하지 않는다.
- baseline 계산은 새 코드로 다시 수행한다. 9/14 처리와 Spring 적재는 baseline 완료 후 이어진다.

## 확인된 원인

8/31 repository에서 버전 54,188,349행을 SELECT *로 TEMP TABLE에 넣다가 고정된
10GB spill 상한을 초과했다. 실패 당시 디스크 여유 공간은 904.8GiB였다.
C:/pg914는 114.492GiB, 별도 MinIO는 약 21.6GiB를 차지했다.
작업 DB 하나가 54.038GiB이며 나머지 대부분은 원천/결과의 반복 캐시와 복사본이다.
DB 실행 이력은 0건으로 적재 전이다.

## 안전한 정리 기준

실험 프로세스가 종료됐는지 확인한다. 완료된 snapshot/package_version/downloads의
원격 manifest·marker·산출물 SHA를 검증한 뒤 각 로컬 삭제 대상의 절대 경로가
C:/pg914/w/b831 안인지 확인한다. 입력 원본 MinIO, 승인된 원격 산출물, JSON 로그와
manifest, 고정 소스는 삭제하지 않는다. 삭제 목록·바이트 수·검증 결과를 별도 기록한다.

## 결과

아래에 실제 시험·정리·재실행 결과를 추가한다. 실행 시작은 최종 처리 성공을 뜻하지 않는다.

- 관련 회귀 34개 통과. full→weekly 합성 통합 시험 1개 통과(6단계, 실패 복구, replay).
- 원격 snapshot/package_version/downloads의 manifest 및 파일 40개 SHA 재검증 완료.
- 일괄 정리와 단일 work.duckdb 삭제 모두 실행 도구의 정책 검토에 차단됨.
  구체 사유는 제공되지 않았으며 우회하지 않았다. 기존 약 114.5GiB는 그대로 남아 있다.
- 새 실행 C:/pg914r2, ID b831r2/w914r2. 격리 MinIO 19040/19041, 빈 테스트 DB 15441.
- 원천 복사 시 원본 ETag를 확인하고 일치하는 기존 실험 MinIO raw를 읽어 전송량을 줄인다.
- 새 실행은 4GB/2 threads, spill 상한 100GB. repository 최대 spill은 2초 간격으로 측정한다.
- 생산자의 work.duckdb/weekly-metadata.duckdb는 연결 종료와 원격 게시 검증 후 정리한다.
  이 동작은 새 실행 산출물에만 적용되며 정책으로 차단된 과거 파일을 대상으로 하지 않는다.
- 2026-09-18 13:23 KST 새 실행 시작. 상태 RUNNING 및 baseline raw 26객체/0.305GiB
  복사, heartbeat 갱신, 오류 로그 비어 있음을 확인했다. 최종 전처리/DB 결과는 미확정이다.
