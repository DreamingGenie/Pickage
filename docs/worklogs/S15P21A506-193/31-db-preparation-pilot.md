# 31. H6 DB 키 연결·0 보완과 격리 적재 검증

## 범위와 계획

2026-09-12 사용자가 다음 단계의 진행을 승인했다. 완료된 CPU Parquet를 사용해
DB 키·날짜를 확인하고 작은 실제 데이터로 적재를 검증한다. 전체 DB 적재는 H7이다.

1. 현재 로컬 DB를 읽기 전용으로 점검한다.
2. 완료 실행·생성 코드·파일 지문을 확인한 뒤 명시한 패키지/날짜만 추출한다.
3. 해당 날짜까지 배포된 적격 버전 목록에 양수 count를 연결해 참조가 없는 버전만 0으로 보완한다.
4. DB package의 ID와 이름, version 복합키, snapshot 날짜를 대조한다.
5. 별도 검증 DB에서 COPY → 검증 → 필요한 행 INSERT / 기존 count UPDATE를 검증한다.
6. 동일 입력 재실행, 0 갱신, 키 누락·변조·오류 시 거부, 다른 지표 보존을 확인한다.

새 모듈은 `historical_db_prepare.py`, `historical_db_probe.py`와 관련 테스트로 분리한다.
기존 H1/H5 생성 코드·완료 결과·서비스 DDL·기존 loader는 변경하지 않는다.
새 의존성을 설치하지 않고 기존 DuckDB와 psql 세션을 사용한다.
이번 pilot은 최대 32개 이름·4개 날짜·100,000행으로 제한하고 `ready_for_load=false`를 유지한다.
별도 `pickage_193_probe_<UUID>` DB만 쓰기 가능하게 제한한다.

## 확인된 DB 계약과 상태

- 서비스 행 키는 `(package_id, version, snapshot_at)`이며 `dependents_count`는 INT NOT NULL이다.
- `(package_id, version)`은 version의 복합 FK, snapshot_at은 snapshot의 FK다.
- snapshot_timestamp는 서비스 컬럼이 아니므로 원천 이력에 보존한다.
- `pickage-267-validation / pickage_267_full_defaulted`는 package-version 게시 이력이 있고
  snapshot 229행이 존재한다. `package_version_snapshot`은 현재 비어 있다.
- 따라서 전체 적재에는 기존 행 갱신뿐 아니라 새 행 INSERT가 필요하다.
- 다른 `pickage_267_full` DB는 기존 실패 실행이며 snapshot 0행이다. 이번 기준으로 사용하지 않는다.
- 기존 데이터 DB에는 SELECT만 실행하고 실제 샘플 적재는 새 격리 DB에서 수행한다.
- 0 포함 전체 날짜 키 수는 큰 규모이므로 이번에는 전체 행을 생성하거나 DB에 적재하지 않는다.
  최종 양수 Parquet와 버전별 최초 포함 날짜를 사용해 필요한 범위만 펼친다.

## 품질와 공개 경계

원본의 미해석 PARTIAL은 그대로 보존한다. 0은 이 계산 정책에서 성공적으로 해석된 참조가
없는 적격 버전이라는 뜻이며 모든 의존 관계가 완전히 해석됐다는 뜻이 아니다.
날짜별 원본 품질은 전체 선정 목록 범위라는 표시와 함께 보존한다.
격리 테스트 성공을 공통 실행 이력 PUBLISHED나 전체 DB 적재 완료로 표시하지 않는다.

## 실제 진행 결과

- DB의 실제 컬럼·PK·FK를 조회해 V1 DDL과 일치함을 확인했다.
- `historical_db_prepare.py`는 완료 실행/생성 계약/입력·출력 파일 지문을 검증하고,
  적격 버전·날짜만 펼쳐 DB의 패키지 ID와 이름, 버전, 날짜와 정확히 대조한다.
- `historical_db_probe.py`는 읽기 전용 카탈로그 조회와 UUID 검증 DB 전용 COPY/UPSERT를 제공한다.
  기존 서비스 DB에 대한 쓰기와 공통 PUBLISHED 이력 등록은 제공하지 않는다.
- 실제 표본: `@types/lodash.get`, `is-number`, `left-pad` / `2022-05-08`, `2026-08-31`.
  준비 8.037초, 78행 = 양수 53행 + 0인 25행. 원본 날짜 품질은 두 날짜 모두 PARTIAL이다.
- 별도 DB `pickage_193_probe_ed1d089ded214a3fa34594c35555925c`에 78행을 적재했다.
  첫 적재 변경 78행(0.354초), 동일 입력 재실행 변경 0행(0.361초), 모든 행 값 일치.
  표본 시간이 전체 10억 행 적재 시간의 추정치는 아니다.
- `package_snapshot`의 별도 검증값 downloads/stars/open_issues가 보존됐다.
  기존 `pickage_267_full_defaulted.package_version_snapshot`은 여전히 비어 있다.
- 최신 코드의 테스트 15개가 10.688초에 통과했다. 0·배포 전 날짜·중복·잘못된 시각,
  DB 키 누락·잘못된 이름·INT 범위·COPY escape·롤백·재실행·쓰기 DB 제한을 확인한다.
- 변경 Python 4개 구문 확인, 독립 읽기 검토에서 pilot 범위의 수정 필요 결함 없음.
  H1/H5 및 전체 CPU 결과 생성 계약은 변경되지 않았다.
- 첫 준비 결과 `data/vd-h6-20260912-01`은 출력 경로 보호 보강 전 산출물로 보존한다.
  최종 검증 대상은 보강 후 생성한 `data/vd-h6-20260912-02`이며 과거 지문을 바꾸지 않았다.
- 실제 DB 생성 직후 로컬 DDL 읽기에서 Windows 기본 cp949 인코딩 오류가 발생했다.
  새로 만든 빈 DB를 확인한 후 UTF-8로 읽어 완료했다. 기존 DB에는 쓰지 않았다.
- [검증 근거와 예시 값](evidence/db-preparation-pilot-results.json),
  로컬 `data/vd-h6-20260912-02/counts.parquet`, `sample_manifest.json`, `probe_result.json`을 보존한다.
  실제 샘플 검증 DB는 확인할 수 있게 남겼으며 자동화 테스트가 만든 DB들은 정리했다.

## 남은 H6/H7 작업

- 전체 선정 버전·날짜의 DB 키 및 원천 게시/달력 이력을 전수 확인해야 한다.
- 날짜 품질의 target 합계로 확인한 0 포함 키는 1,007,084,608행이다.
  양수 296,325,102행과 0인 710,759,506행이며, 실제 DB 적재는 아직 수행하지 않았다.
- 전체 적재기는 이 범위를 날짜/패키지 묶음으로 생성·적재하며 공통 실행 이력,
  PARTIAL 품질·입력 지문·트랜잭션·완료 후 재개·게시 경계를 구현해야 한다.
- 이번 작은 검증용 함수를 한도만 풀어 전체 DB에 사용하지 않는다.
  서비스 DDL과 기존 데이터는 보존하고 전체 적재 승인 시 별도 H7 경로로 진행한다.
