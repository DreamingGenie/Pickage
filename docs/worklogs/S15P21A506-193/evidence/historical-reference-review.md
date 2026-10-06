# H2 기준 구현 검토

- 검토일: 2026-09-10
- 검토자: 별도 agent `task08_diagnostic_review`
- 범위: `historical_reference.py`, 전용 테스트, fixture, 12번 결과 문서의 구현 범위
- 결론: PASS. 핵심 계산의 P1 차단 결함 없음

날짜별 source/target 선별·npm worker 재사용·stable target·0 포함·DISTINCT edge·상태 우선순위·
오류 source의 성공 edge 보존·alias/prerelease/protocol 정책·UTC 경계·동률·직접/self-edge·
실행 상한·fixture/code SHA 보존을 확인했다. H3 interval/delta와 독립적인 계산 구조다.

P2 계약 관찰: 마지막 calendar 시각이 observed와 같은지는 강제하지 않는다.
처리: 소형 비교에서 과거 날짜 일부만 선택하는 것을 허용하는 의도임을 README와 결과 문서에
명시했다. 관측 시각과 calendar를 유지·축소한 결과가 기존 결과의 해당 부분과 정확히 같은지
회귀 테스트를 추가하고 통과했다. 실제 H1의 전체 calendar 계약은 변경하지 않았다.

추가 테스트 보강: tie 선언이 첫날부터 존재하게 하여 `NO_ELIGIBLE_TARGET → 1.0.0+z →
1.0.0+aa`를 각각 검증했다. 최종 전체 테스트 96개가 통과했다.

실제 전체 데이터의 정확성·H3 최적화 성능·DB 적재 검토를 의미하지 않는다.
