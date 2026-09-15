# 서버 표본 이관 검증 결과

이 문서는 해당 단계 당시의 계획·검증 기록이다. 이후 서버 복원과 서비스 DB 전환을 완료했으며, 현재 상태와 검증 범위는 [최종 결과](12-final-result.md)를 따른다. 당시 실패·미실행 기록은 이력으로 보존한다.

2026-09-14. **서버 표본 이관 PASS. 전체 데이터 이관·서비스 연결 전환은 미실행.**

## 이번에 확인한 흐름

1. 원본 로컬 DB를 재시작하지 않고 별도 덤프 클라이언트를 연결했다. host 포트와 원본 데이터 볼륨 설정을 바꾸지 않았다.
2. 검증된 작은 archive와 실행 도구·기존 Flyway/JDBC JAR를 서버의 작업 전용 폴더로 보냈다.
3. 최초 전송에서 1MiB만 먼저 보내고 SFTP `put -a`로 나머지를 이어 보냈다. 완성 파일 SHA-256이 원본과 일치했다.
4. 기존 서비스 DB `pickage`를 작은 custom dump로 백업하고 별도 후보 DB에 복제했다.
5. 실제 V1 이력(checksum `-1434735067`)을 Flyway validate로 확인한 다음 후보의 빈 테이블만 제거했다.
6. 표본을 pre-data → data → post-data로 복원하고, V2~V6 및 Flyway validate를 실행했다.
7. 부모·자식 구조와 표본의 모든 값을 검사했다. 원래 서비스 DB와 API 연결은 유지했다.

Java는 기존 API 이미지 `pickage-api:manual-01`의 Java 21 런타임을 일회성 컨테이너에서 사용했다. API 자체를 시작하지 않았다. Flyway는 로컬과 같은 11.14.1, JDBC는 42.7.11을 사용했다. 비밀번호는 기존 PostgreSQL 컨테이너 환경에서 프로세스 내부로만 전달했으며 파일이나 명령 인자에 넣지 않았다.

## 표본 결과

| 테이블 | 서버 복원 후 |
| --- | ---: |
| package | 3 |
| version | 541 |
| snapshot | 3 |
| package_snapshot | 9 |
| package_version_snapshot | 1,623 |

pino/react/winston, 최근 날짜 3개의 총 **2,179행**을 비교했다. 모든 키와 값이 일치했다. 서버 PostgreSQL 16.15에서 V1~V6 성공 이력과 날짜별 자식 파티션 3개를 확인했다.

원래 `pickage`의 다섯 테이블은 전후 모두 0행이다. V1 이력 전체 값과 public 객체 OID/종류 목록도 그대로다. 기존 API `/actuator/health`는 `UP`이었으며 API 재시작·DB_URL 변경은 하지 않았다.

## 발견한 문제와 수정

첫 실행은 version CSV 전체 바이트 비교에서 실패했다. 조사 결과 541개 버전의 키·값은 모두 같고 **행 정렬 순서만 달랐다**. 로컬과 서버 모두 `en_US.utf8`을 사용하지만 PostgreSQL 기반 이미지가 Alpine과 Debian으로 다르다. 같은 collation 이름만으로 결과 행 순서까지 같다고 가정할 수 없다는 실제 관측이다.

서버 파일럿의 비교는 PK로 레코드를 대응시키도록 수정했다. 각 레코드의 원래 CSV 표현을 비교하므로 NULL/따옴표로 감싼 빈 문자열, JSON, 여러 줄 문자열을 그대로 구분한다. 순서가 달라도 같게 판단하되 값 변조·중복 키·NULL/빈 문자열 변경은 잡는 시험을 추가했다. 수정 후 새 후보 DB에서 전체 절차를 다시 수행해 통과했다.

로컬 보조 컨테이너는 개별 probe의 `-h`만으로 연결됐지만 일반 덤프 도구에는 호스트 설정이 전달되지 않는 문제가 있었다. `PGHOST=127.0.0.1`을 보조 컨테이너에 고정하고, 호스트 옵션 없는 psql/pg_dump 연결까지 확인했다. 원본 컨테이너는 그대로 유지했다.

## 측정값과 한계

| 구간/항목 | 측정 |
| --- | ---: |
| 서버 절차 전체(전송 제외) | 9.343초 |
| 기존 DB 백업 | 0.167초 |
| 표본 복원 도구(사전 검사 포함) | 1.107초 |
| Flyway V2~V6 적용 | 1.457초 |
| 표본 전체 값 비교 | 1.147초 |
| 후보 DB 물리 크기 | 9,198,615바이트, 약 8.77MiB |
| PostgreSQL cgroup 표본 최대 메모리 | 101,007,360바이트, 약 96.33MiB |
| PostgreSQL 메모리 제한 | 2GiB, 변경 없음 |
| pg_stat_wal wal_bytes 전후 차이 | 5,219,653바이트 |

메모리는 기존 PostgreSQL cgroup(페이지 캐시 포함)을 100ms 간격으로 관측한 최대값이다. Flyway 보조 JVM의 메모리를 합친 값이 아니며, WAL 수치도 클러스터 전체 누계의 차이다. 다른 서비스와의 자원 공유를 고려해야 한다.

표본 archive는 32,406바이트이며 실행용 JAR 등을 포함한 업로드 묶음은 약 4.67MB다. 최초 묶음의 나머지 약 3.62MB를 이어 보내는 데 0.721초가 걸렸다. **어느 값도 전체 약 144.6GiB 이관의 처리량이나 예상 시간을 대표하지 않는다.**

전체 이관 시간을 산정하려면 큰 단일 테이블과 인덱스 작업을 포함한 더 큰 표본, 임시/WAL 디스크 사용량, 실제 지속 업로드 속도를 추가 측정해야 한다. 현재는 작은 데이터로 실행 경로의 정확성을 검증한 단계다.

## 남겨 둔 실행 결과

- 성공 후보 DB: `pickage_import_341_server_pilot_cc25a3fda284`
- 첫 실행 후보 DB: `pickage_import_341_server_pilot_45dea13b668a` — CSV 정렬 비교 단계에서 실패한 상태로 보존. 서비스 연결에 사용하지 않는다.
- 서버 성공 실행 폴더: `/home/ubuntu/service-data-migration/341/server-pilot-20260914-02`
- 서버 첫 실행 폴더: `/home/ubuntu/service-data-migration/341/server-pilot-20260914-01`
- 두 폴더에 source archive, 기존 서비스 DB의 작은 백업, 파일 해시, Flyway/복원 로그와 결과 JSON을 보존했다.
- 로컬 결과: `data/service-data-migration/server-pilot-01/server-result.json`, `server-pilot-02/server-result.json`. Git 제외 경로다.
- 서버의 이관용 보조 컨테이너는 종료했다. 로컬 덤프 보조 컨테이너는 다음 덤프를 위해 대기 상태로 유지한다.

최초 묶음 SHA-256: `64fd0a3748f64172ef4a03ecc5fbd07d9b25796073ede9c9d3eff616619bd625`.
수정된 두 번째 묶음 SHA-256: `1ae9c5d038a7d777dd650dd05007bf78b260c533f0ab330f7c654d5943333c4a`.

## 코드와 재현 경계

- [로컬 클라이언트](../../../scripts/service-data-migration/local_dump_client.py), [연결·경로 안내](04-local-dump-access.md)
- [서버 표본 실행기](../../../scripts/service-data-migration/server_pilot.py), [후보 전용 Flyway 실행기](../../../scripts/service-data-migration/CandidateFlyway.java)
- [정렬/값 비교 시험](../../../tests/test_server_pilot.py), [클라이언트 연결 보호 시험](../../../tests/test_local_dump_client.py)

서버 실행기는 작은 파일럿 묶음만 받는다. `bundle-manifest.json`의 파일 해시, archive 20MiB 이하, 새 실행 폴더, 기존 V1/0행 상태를 검사한다. 기존 결과 파일이 있으면 재실행을 거부한다. 실패한 DB의 부분 재개 대신 새 후보 DB를 사용한다. 묶음 생성·업로드·SHA 확인 후 서버에서 실행하는 명령은 다음과 같다.

```bash
python3 /home/ubuntu/service-data-migration/341/<새-실행폴더>/server_pilot.py \
  --work-dir /home/ubuntu/service-data-migration/341/<새-실행폴더>
```

이번 실행은 SSH와 분리된 프로세스로 기동하고 PID/로그를 남겼다. 원래 DB 교체, 전체 덤프/적재, API 연결 전환, 배치 자동화는 실행하지 않았다. `ready_for_service=false`, `full_transfer_ready=false`를 유지한다.
