# 실제 산출물 입력 연결 — 병렬 준비

2026-09-12 사용자는 기존 작업과 병렬 가능한 **입력 연결 코드·작은 샘플 테스트** 진행을 승인했다.
Jira 연결 보류 결정은 유지한다. 원래 적재 코드/DB, 전수 파일 해시, 원격 호출은 범위 밖이다.

## 변경 범위와 작업 순서

1. 현재 커밋의 producer별 manifest·완료 표식·선택 함수와 실제 파일 읽기 경계를 조사한다.
2. 로컬에 명시적으로 복사한 작은 메타데이터만 제공하는 읽기 전용 연결 계층을 만든다.
3. 안정된 native 선택 함수를 재사용해 run ID·snapshot 시각·pin SHA·기대 건수와 파일 목록을 대조한다.
4. 명시적으로 선택한 작은 Parquet만 크기·SHA·스키마·행 수를 검사한다. 요청하지 않은 파일은 열지 않는다.
5. 작은 native 형식 샘플과 누락/변조/잘못된 run/과도한 크기 테스트를 수행하고 결과를 기록한다.

소유 경로는 `pipeline/integrity_validation/`와 이 worklog뿐이다. 이전 합성 검증 기능을 보존한다.
추가 의존성·DB/Docker 접속·원천 데이터 수정·8번 적재 모듈 복사는 수행하지 않는다.

## 증거 범위

- manifest SHA는 사용자가 지정한 pin과 비교한다. 파일이 없는데 현재 코드 hash를 채워 넣지 않는다.
- `build_contract_sha256`과 validator contract를 혼동하지 않는다. metadata 통과는 원천 생성의 승인이 아니다.
- 메타데이터 검증과 작은 파일 검증, 모집단 전체 검증, 서비스 공개 승인을 서로 다른 상태로 남긴다.
- 지정하지 않은 원천 파일은 읽지 않으며 전체 native validator·생산 적재 준비 함수를 호출하지 않는다.
- snapshot candidate의 기존 `read_candidate`는 Projects 전체 footer를 읽으므로 이번 경로에서 호출하지 않는다.
- 8번 historical loader의 변경 중인 코드와 전체 검증에 결합하지 않는다. 지원하지 않는 형식은 명시적으로 거부한다.

## 완료 기준

기존 합성 테스트 통과, 안정된 native manifest 연결·독립 pin·표식·샘플 파일 불일치 검출,
읽기 경로·메모리·크기 제한, 원래 작업 보호, 읽은 것과 미검증 범위를 구분한 보고서 생성.
실제 대용량 산출물 검증이나 9번 전체 완료를 주장하지 않는다.

## 실제 진행

- 현재 9번 브랜치 `codex/09-integrity-validation`, HEAD `065fb8e` 및 기존 미커밋 작업 확인.
- package/version과 observed package_snapshot의 `select_run`은 작은 metadata 조회만 수행함을 확인.
- snapshot reference 및 dependents의 기존 전체 validator는 대량 원천 검사를 수행하므로 별도 연결 대상으로 보류.
- 로컬 metadata 연결·선택한 작은 Parquet 검사·예제 생성·오류 테스트 구현 완료.
- 독립 검토에서 발견한 시각 정밀도 잘림을 기존 snapshot 정책 parser 재사용으로 수정했다.
  요청뿐 아니라 원문 manifest의 시각도 검사하며, 이 정책 코드를 validator SHA에 포함했다.
- 최종 실제 결과와 미실행 범위는 [결과 기록](03-native-input-results.md)에 남긴다.
