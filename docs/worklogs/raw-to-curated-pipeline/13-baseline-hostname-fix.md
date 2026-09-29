# 기존 방식 격리 컨테이너 hostname 수정

## 변경 범위와 계획
1,000개 실험의 Spark는 성공했지만 기존 방식 repository의 Java 시작 시 컨테이너 hostname을 해석하지 못해 실패했다. baseline에만 고정 hostname과 127.0.0.1 hosts 매핑을 설정한다. network none과 기존 CPU/RAM/swap 제한은 유지한다.

실행기 옵션 회귀 테스트와 같은 이미지·네트워크 조건에서 Java 및 local Spark 기동을 검증한다. 로컬 Docker daemon이 실행되지 않아, 기존 사용자 승인 범위의 data EC2에서 자원이 제한된 일회성 실험 컨테이너로 검증한다. 운영 배포와 이전 결과는 변경하지 않는다. 전체 성능 실험 재실행은 이번 검증과 구분한다.

## 실제 수행 및 결과
진행 중.

- baseline 실행에만 --hostname <run>-baseline 및 --add-host <hostname>:127.0.0.1을 추가했다. network none, CPU 3, RAM 7680MiB 및 swap 0 유지.
- 실행기 회귀 테스트 1개 통과: 네트워크 격리, loopback 이름 매핑, CPU/RAM 및 기존 환경 옵션 보존 검증.
- data EC2 동일 이미지·network none·동일 자원 상한에서 실제 기동 확인: HOSTNAME_RESOLVED=127.0.0.1, JAVA_HOSTNAME=127.0.0.1, LOCAL_SPARK_VERIFIED local[2], 1,000행 count 통과, exit 0. S3 credential 환경 분기도 가짜 값으로 활성화했고 외부 접근은 하지 않았다.
- 일회성 검증 컨테이너 제거 완료, 운영 MinIO/mlflow healthy. 이전 실험 코드·입력·측정 결과를 덮어쓰지 않았다. 전체 벤치마크는 재시작하지 않았다.

## 1,000개 성능 비교 재시작
- 사용자 재시작 요청에 따라 sample1000-ec2-20260916-a2 새 실행으로 준비 → 두 EC2 Spark → 기존 방식 → 정확 비교를 수행한다. a1 코드·입력·결과는 보존한다.
- 표본 seed/선정 규칙/크기 1000 및 CPU·RAM 제한은 유지한다. hostname 수정이 반영된 코드를 두 서버에 동일하게 고정하며 운영 배포는 변경하지 않는다.
- 재시작 전 두 서버 운영 컨테이너 정상 상태 및 디스크 여유(data 116GiB/app 129.8GiB) 확인. 실행기 회귀 테스트 7개 통과.
- 양 호스트 코드 SHA256 5381ae66af4bf78730c77ba73b22ba6b06228428bfc8c60211f63e7ec8c07535 일치 확인. app PID 1406019/data PID 2840729로 백그라운드 시작.
- 착수 확인: data RUNNING/prepare 및 BENCHMARK_PHASE_STARTED prepare, app master 대기. 양쪽 guard issue=null/consecutive_issues=0. 아직 이번 실행의 성능 결과와 정확 비교 결과는 미확정이다.

## a2 완료 확인 및 측정 결과
- 서버 result COMPLETE, benchmark-result VERIFIED, 22개 출력 그룹 EXACT_CANONICAL_ROW_MULTISET=EQUAL. JSON 표현/UTC timestamp/컬럼 순서 정규화 후 행 중복을 포함해 비교했으며 파일 byte 동일성은 비교하지 않는다. 완료 2026-09-16 14:22 KST.
- 표본 1,000 package, raw versions 106,393, curated version 40,417. 전체 준비 464.438초, Spark phase 455.899초, baseline phase 56.839초, compare 206.045초. 처리 phase 기준 기존 방식이 약 8.02배 빠름.
- 단계별 baseline/Spark 초: package_version 2.912/194.591; downloads 0.248/44.412; repository 43.867/62.872; package_snapshot 0.711/13.334; dependents 4.350/105.482.
- cgroup 메모리 peak bytes: baseline 2413502464; Spark driver 1359548416, data worker 1865949184, app worker 2026401792, master 189054976. 각 컨테이너 개별 peak이며 합은 동시 최대 메모리가 아니다. CPU 사용량 초: baseline 116.173; Spark driver 217.226/data worker 233.138/app worker 183.520/master 9.874(각 컨테이너 수명 측정).
- 실험 컨테이너 정리 완료, data/app guard FINISHED, app EXPECTED_MASTER_STOP/error=null, cleanup_errors 없음. 운영 서비스 healthy. DB 및 공식 Curated 게시 없음.
- 해석 한계: 반복 1회, 고정 단계 입력 비교(전체 체인 아님), 기존 방식 로컬 파일 vs 분산 Spark MinIO 입출력 포함. 기존 방식 repository도 local Spark 사용. 작은 표본 결과를 전체 스냅샷 또는 엔진 자체 성능으로 일반화하지 않는다.
