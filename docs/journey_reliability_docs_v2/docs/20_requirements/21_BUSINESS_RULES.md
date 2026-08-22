---
doc_id: JR-DOC-021
title: Business Rules
version: 1.1
status: LOCKED
owner: PM
last_updated: 2026-08-22
depends_on:
  - JR-DOC-002
  - JR-DOC-020
source_of_truth_for:
  - business-rules
supersedes: []
---

# Business Rules

## Input / Scope

**BR-001** target arrival은 현재보다 미래여야 한다.  
**BR-002** target reliability 미지정 시 90%를 사용한다.  
**BR-003** 지원 geography 밖의 Journey를 서울 전체 지원처럼 계산하지 않는다.  
**BR-004** structural route는 route provider 결과에서 선택하며 route provider ETA 자체를 Ground Truth로 간주하지 않는다.  
**BR-005** route selection은 provider order를 유지하며 현재 지원범위에서 해석 가능한 첫 candidate를 선택한다. Reliability score로 route를 재정렬하지 않는다.

## Probability

**BR-010** Probability는 source/support/fallback metadata 없이 사용자 결과로 노출하지 않는다.  
**BR-011** P50/P90은 final-arrival distribution percentile이다.  
**BR-012** P90을 probability value와 혼동하지 않는다.  
**BR-013** planned connection success와 final on-time probability는 서로 다른 metric이다.  
**BR-014** small-N 여부는 숨기지 않는다.  
**BR-015** Minimum Support threshold는 calibration 전 임의 정수로 고정하지 않는다.  
**BR-016** WALK point estimate를 empirical uncertainty distribution으로 표시하지 않는다.  
**BR-017** static transfer time을 개인별 transfer distribution으로 표시하지 않는다.  
**BR-018** synthetic/amplified replay를 model truth로 사용하지 않는다.

## Recommended Departure

**BR-020** recommended departure는 selected structural route conditional 결과다.  
**BR-021** depart time이 바뀌면 feasible vehicle/train candidate를 재평가한다.  
**BR-022** 동일 distribution을 단순 shift해서 recommended departure를 만들지 않는다.  
**BR-023** service-discrete probability가 monotonic이라고 증명되지 않은 상태에서 binary search를 정확성 전제로 사용하지 않는다.  
**BR-024** 필요한 source/schedule가 부족하면 recommended departure는 unavailable이 될 수 있다.  
**BR-025** 미래 bus WAIT는 exact future vehicle ID를 필수로 하지 않으며 time-conditioned empirical wait/headway를 허용한다.  
**BR-026** 미래 subway WAIT는 검증된 timetable 또는 empirical headway를 사용하고 source version을 기록한다.

## Transfer / Wait

**BR-030** TransferLeg에는 다음 vehicle/train의 wait를 포함하지 않는다.  
**BR-031** WaitLeg는 boarding point 도착 이후부터 시작한다.  
**BR-032** `BUS_TO_SUBWAY`, `SUBWAY_TO_BUS`, `SUBWAY_TO_SUBWAY`는 별도 TransferType이다.  
**BR-033** transfer miss는 물리적 transfer 자체의 실패가 아니라 boarding feasibility 결과로 판정한다.  
**BR-034** Tier-0 miss rule은 fixed buffer이고, 실측 headway 기반으로 upgrade하기 전 version을 유지한다.  
**BR-035** WALK/Transfer endpoint는 coordinate role/source를 기록하며 station center와 exit/platform을 동일시하지 않는다.  
**BR-036** `BUS_TO_SUBWAY`와 `SUBWAY_TO_BUS`는 street component와 station-internal component의 source/fallback을 구분한다.

## Reforecast

**BR-040** 완료된 leg는 Reforecast에서 다시 sample하지 않는다.  
**BR-041** confirmed UserEvent는 사실로 고정한다.  
**BR-042** `BUS_SKIPPED`는 personal boarding-failure probability가 아니다.  
**BR-043** same UserEvent는 idempotent하게 처리한다.  
**BR-044** Reforecast 결과는 이전 snapshot과 별도 version으로 저장한다.

## Source / Evidence

**BR-050** Transit reliability core는 PD-003 source policy를 따른다.  
**BR-051** TMAP은 WALK utility이며 transit reliability label source가 아니다.  
**BR-052** `VERIFIED` claim은 Evidence ID가 있어야 한다.  
**BR-053** corridor-scoped Evidence를 citywide claim에 사용하지 않는다.  
**BR-054** source timestamp와 collector received time을 구분한다.  
**BR-055** raw payload는 parser 실패 전에도 보존한다.

## UX / Honesty

**BR-060** 실제 probability는 whole-percent 수준으로 표시하는 것을 기본으로 한다.  
**BR-061** illustrative number는 실제 runtime result처럼 보이게 사용하지 않는다.  
**BR-062** low support/fallback/stale state를 사용자에게 숨기지 않는다.  
**BR-063** “가장 안전한 경로”, “서울 전체 정확도” 같은 미검증 문구를 사용하지 않는다.  
**BR-064** AI 설명은 deterministic result/evidence를 바꾸지 않는다.  
**BR-065** leg-level calibration만으로 whole-Journey probability를 `calibrated`라고 표시하지 않는다.  
**BR-066** Journey result는 validation scope를 노출 가능한 metadata로 보유한다.

## Demo

**BR-070** Final Demo probability는 실제 pipeline output만 사용한다.  
**BR-071** Route B realtime E2E 미완료 시 `SUBWAY_TO_BUS VERIFIED`라고 발표하지 않는다.  
**BR-072** distributed proof는 실제 worker participation과 correctness evidence가 있어야 한다.
