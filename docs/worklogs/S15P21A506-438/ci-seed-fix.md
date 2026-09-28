# V12 추가 후 CI 시드 초기화 오류

## 변경범위와 작업계획
- 첨부 CI 로그의 두 CommunityAcceptanceIntegrationTest 실패를 해결한다.
- available_package FK를 유지하고 package 초기화 TRUNCATE 목록에 참조 테이블을 명시한다.
- 기존 작업 폴더의 테스트·seed_mock_parity·seed_reset 수정은 보존한다. 누락된 seed_sample·seed_service_full을 보완한다.
- 별도 PostgreSQL 테스트 컨테이너에서 기존 통합 테스트로 검증한다. 운영 DB와 서비스 데이터는 변경하지 않는다.

## 이슈와 해결방법
- V12가 package를 참조하는 available_package를 추가했지만 기존 초기화 목록에는 없었다.
- ON DELETE CASCADE는 TRUNCATE의 참조 테이블 지정 요구를 대체하지 않는다.
- 범위를 넓히는 TRUNCATE CASCADE 대신 시드 네 개와 기존 테스트의 명시적 목록을 맞춘다.
- 브랜치 이슈는 S15P21A506-438이다. Jira 도구가 없어 원격 검색·코멘트·상태 변경은 미실행이다.

## 실제 진행한 작업과 결과
- CI 로그와 기존 수정 내용을 확인했다. seed_sample.sql과 seed_service_full.sql의 누락을 보완했다.
- Java 21 컨테이너 + 별도 PostgreSQL 16 컨테이너에서 `./gradlew --no-daemon integrationTest --tests '*CommunityAcceptanceIntegrationTest'` 실행: BUILD SUCCESSFUL (7분 16초).
- V1~V12 migration과 시드 네 개를 실행하는 기존 회귀 테스트를 포함해 검증했다. `git diff --check` 통과.
- 테스트 전용 PostgreSQL 컨테이너·익명 볼륨·네트워크는 검증 후 제거했다.
- 전체 integrationTest·원격 CI 재실행·운영 배포·commit/push는 미실행이다.
