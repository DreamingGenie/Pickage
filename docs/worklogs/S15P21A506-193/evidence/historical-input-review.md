# H1 입력 준비 코드 독립 검토

- 날짜: 2026-09-10
- 구현: root. 테스트 독립 작성: task08_diagnostic_input. 읽기 전용 검토: task08_diagnostic_review.
- 대상: `pipeline/version_dependents/historical_input.py`, 전용 테스트와 README.
- 최종 판정: **PASS**. 실제 전체 실행 결과의 검증과는 별개다.

최초 검토에서 기대 calendar 개수·최신 시각의 명시적 검사와 imported helper 코드의 계보가
부족하다고 지적했다. 실행을 37.75초에 중단하고 원본과 실패 디렉터리를 보존했다. wrapper에
기대 기준일 개수(이번 실행 229)와 마지막 시각==관측 시각 검사를 추가하고, helper를 포함한
7개 코드 파일의 시작/종료 해시와 Python/DuckDB 버전을 기록했다.

실패 경로를 새 실행 ID로 재시도하는 계약을 문서화하고 테스트했다. prerelease/invalid 버전은
source population에 패키지 ID·이름·버전이 남으므로 version별 semver 분류와 연결해 제외 원인을
역추적할 수 있음을 설명했다. 별도 제외 대상을 중복 저장하지 않았다.

재검토에서 위 보완과 ASOF/UTC/NULL·future/provenance/보존식/파일 SHA·독립 birth histogram 검증
경로를 확인했으며 남은 P1 correctness blocker를 발견하지 못했다. 실제 v2 실행·성능·수치는
실행 영수증과 별도 파일 검증으로 확인해야 한다.
