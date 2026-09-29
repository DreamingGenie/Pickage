# develop 병합 확인 — 2026-09-28

- 대상 브랜치: data/feat/S15P21A506-372-raw-to-curated-pipeline
- 병합 전 HEAD: 0c99d9f / MERGE_HEAD: 004388384e1450654e89f7594f5a51c872f910d9
- 사용자 요청: 시작한 develop 병합을 검토하고 문제가 없으면 머지 커밋.
- 충돌6개: 배포/MinIO/패키지 스냅샷 문서3개, historical DB migration 테스트1개, 새 downloads reload 파일/테스트 경로2개.
- 해결: 양쪽 문서 변경 보존, V1~V3 명시 선택과 REPO_ROOT 결합, downloads DB reload를 postgresql 모듈/테스트 디렉터리에 배치하고 import·계약 해시 경로를 갱신.
- Python 관련 테스트: 63개 실행, 37개 통과·26개 환경 의존 검사 건너뜀. downloads reload, historical DB keys/fast publish, dispatcher, resource budget, workspace 대상.
- 모니터링 테스트: curated·weekly·config 18개 통과. 로컬 테스트 환경에 기존 requirements의 PyYAML을 설치한 뒤 실행.
- Java 검증: `gradlew.bat test --tests 'com.ssafy.pickage.domain.curatedload.*' curatedBootJar --console=plain` 성공, Curated 단위 테스트 18개 통과.
- 배포 확인: 임시 검증용 환경값으로 data compose `config --quiet --no-env-resolution` 통과. 실제 비밀 파일·서버 연결 검증은 아님. weekly→bounded dispatcher 연결, 모니터링 객체 경로, MinIO api-loader 자격증명 파일명 일치 확인.
- 제한: Docker Desktop Linux 엔진이 꺼져 있어 PostgreSQL 통합 테스트와 컨테이너 실행 검증은 미실행. 기존 적재 DB와 서버는 변경하지 않음. develop 전체 기능 및 대용량 데이터 재실행은 이번 병합 검증 범위 밖.
- 공백 검사: 충돌 해결·신규 기록 파일은 통과. 전체 병합 diff에는 develop의 473 문서 및 475 원본 실행 로그에 기존 공백 경고가 있으며 해당 기록은 수정하지 않음.
- 추가 병합 오류: develop의 V8 dependent_transition과 브랜치의 V8 curated_load_staging 번호 충돌 발견. 운영 미반영 Curated staging을 V14로 이동하고 적재 안내에 기존 로컬 V8 실험 DB 재사용 제한 기록. SQL 본문은 보존하고 마이그레이션 번호 중복을 재검사.
