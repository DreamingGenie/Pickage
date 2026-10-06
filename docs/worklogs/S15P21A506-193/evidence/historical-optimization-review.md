# H3 계산 핵심 검토

- 날짜: 2026-09-10
- 검토자: 별도 agent `historical_review`
- 최종 판정: PASS — 작은 fixture와 로컬 DuckDB 계산 핵심 범위

초기 검토에서 미매핑 패키지에 후보가 함께 전달되면 RESOLVED가 될 수 있는 모순 입력을
발견했다. 해당 입력은 명시적으로 거부하며 테스트로 확인했다. 미매핑 정상 선언의 상태는
기존 `UNMAPPED_TARGET_PACKAGE`다. 입력의 source/선언 index·status·target·누락·gap·overlap
검증도 보강했다. metric을 `reference_resolution_calls`로 명확히 표시했다.

두 interval window의 정렬에 declaration index가 포함되어 동일 시작/종료 구간을 안정적으로
합치는 것을 재검토했다. 120 source × 2 선언 × 4 구간에서 매 날짜 count 120, 합친 관계
구간 480을 확인했다. nested/adjacent 합집합, 중복, self/직접 관계, 늦은 후보, 동률 및 미해석
변화, 입력 순서/패키지 파티션 순서의 불변성도 통과했다.

최종 `_insert_fixture_rows` adapter 변경을 추가 검토했다. 테이블은 내부 allowlist로
제한되고 DESCRIBE의 타입을 사용하며 데이터/schema는 파라미터로 전달된다. NULL·BOOLEAN·
INTEGER·BIGINT·VARCHAR 및 선언 name/range/target의 NULL 보존을 직접 확인했다.

전체 suite 121개 통과는 root의 `historical-optimization-validation.json`에 기록했다.
반복 예제 H2/H3의 모든 count·선언/source·품질·runtime 지문이 일치하고 최종 중간값은
1.859초 / 0.219초다. 이 검토는 실제 전체 229일 계산, 생산 Parquet 재개·저장, DB 적재 또는
대용량 성능의 완료 판정이 아니다.
