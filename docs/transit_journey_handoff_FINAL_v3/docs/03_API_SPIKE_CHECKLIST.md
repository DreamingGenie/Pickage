# Phase 0 API Spike Checklist

> 이 문서는 API를 "호출했다"에서 끝내지 않고, 최종 확률 계산에 실제로 쓸 수 있는지 판정하기 위한 체크리스트다.

## 공통 저장 규칙

모든 endpoint에 대해:

- [ ] HTTP status
- [ ] API business result code/message
- [ ] request timestamp
- [ ] receive timestamp
- [ ] source-generated timestamp가 있으면 분리 저장
- [ ] raw body 저장 (secret 제거)
- [ ] raw body hash
- [ ] row/item count
- [ ] empty response인지
- [ ] duplicate source snapshot인지
- [ ] schema version / collector version
- [ ] latency

샘플 파일명 권장:

`data/samples/<provider>/<api>/<yyyy-mm-dd>/<hhmmss>_<request-id>.json`

원본 XML이면 `.xml`을 그대로 보존하고 normalized JSON은 별도 생성.

---

## A. Bus Arrival

Official: https://www.data.go.kr/data/15000314/openapi.do

### 확인

- [x] route-wide endpoint 실제 명칭 — `getArrInfoByRouteAll` (D-013)
- [x] `busRouteId` (D-013)
- [x] `stId`, `staOrd` — 실제 응답에 그대로 존재함 (`arsId`와 별개 필드로 둘 다 있음, D-038 raw item에서 확인)
- [x] `vehId1`, `vehId2` (D-013/D-014)
- [x] `exps1`, `exps2` (실 응답 schema에 포함, PHASE0 A절)
- [x] `mkTm` (D-015 — call-level, per-stop 아님)
- [ ] first/second bus semantics
- [x] same source timestamp repeated responses (D-015 — 104개 item 동일 `mkTm`)
- [ ] source timestamp timezone/format
- [ ] expired ETA on receipt

### 산출

- `bus_arrival_schema.md`
- sample raw
- unique source snapshot ratio

---

## B. Bus Position

Official: https://www.data.go.kr/data/15000332/openapi.do

### 확인

- [x] 실제 endpoint 명 — `getBusPosByRouteSt` (`getBusPosByRtid`도 `...List`도 아님, D-011)
- [x] `vehId` (D-013)
- [x] `plainNo` (D-014)
- [x] `sectOrd` (D-014)
- [x] `sectionId` (D-014)
- [x] `stopFlag` (D-014/D-020 — 0→1 전이 49건 관측)
- [x] `nextStId` — **응답에 없음, 확인 완료** (D-014)
- [x] `nextStTm` 실제 포함 여부 — **미포함으로 확정** (D-014)
- [x] `dataTm` (D-014/D-015 — vehicle별로 다름)
- [x] `rtDist`, distance fields — **응답에 없음, 확인 완료** (D-014)
- [x] congestion/full-related fields 실제 제공/semantics (D-014 — `congetion` 오탈자, `isFullFlag`)
- [ ] turnaround/up-down 판정 필드

### 핵심 테스트

Arrival `vehId1/2`와 Position `vehId` 집합 일치율. **완료 — 100% (2026/2026), route 753, ~10분 지속수집 (D-020)**

---

## C. Bus Actual / Residual

### Actual rule 후보

`stopFlag=0 → stopFlag=1` + target stop/section transition.

반드시 interval로 보존.

- [x] lower/upper source time (D-020 — `dataTm` 기준 interval bound)
- [x] interval width (D-020 — 대부분 20~40초 폭)
- [ ] impossible transitions
- [ ] same vehicle trip boundary

### Residual

`Actual - Predicted`

- [ ] lower/mid/upper residual — **미착수**, Phase 0 GO 이후 vertical slice 단계 항목
- [ ] lead time
- [ ] event weighting issue (prediction snapshot 많은 actual event가 전체를 지배하지 않도록 주의)

---

## D. Subway Arrival

Official: https://data.seoul.go.kr/dataList/OA-15799/A/1/datasetView.do

Sample service documented by Seoul:

`realtimeStationArrival/ALL`

### 후보 필드

- [x] `subwayId` (D-016/D-021/D-034 — 1,2,3호선에서 확인)
- [x] `updnLine` (D-027)
- [x] `statnId` (D-016)
- [x] `statnNm`
- [ ] `barvlDt` — 존재 확인만 됨, negative/zero 케이스 미검토
- [x] `btrainNo` (D-017)
- [ ] `btrainSttus` — 실제 값 semantics 미검토
- [ ] `bstatnId`, `bstatnNm` — TO_VERIFY (ID_MAPPING.md에 명시)
- [x] `recptnDt` (D-016 — per-train)
- [x] `arvlMsg2` (D-018, D-032 — 카운트다운/역수 메시지)
- [x] `arvlCd` (D-018/D-021/D-034 — `{0,1,2,3,4,5,99}` 상태머신, 3개 노선 교차확인, `SUBWAY_ACTUAL_RULE_V0.md`)
- [ ] `lstcarAt`

### 품질

- [ ] 동일 `recptnDt` 반복
- [x] train number 누락 — 조사 완료하나 원인 일부 미상 (D-023 페이지네이션 원인 확정, D-026/D-032/D-033 2호선 특정 station code `1002000201` 갭은 원인 미상으로 이월)
- [ ] 역/호선별 item density
- [ ] barvlDt negative/zero/unexpected
- [ ] API latency

---

## E. Subway Position

Official: https://data.seoul.go.kr/dataList/OA-12601/A/1/datasetView.do

### 반드시 실제 response로 확인

- [x] train number field (`trainNo`, D-017)
- [x] line field (`subwayId`, D-021/D-034)
- [x] direction (`updnLine`, D-027)
- [x] station/current position (`statnId`, D-023)
- [x] train status sequence (`trainSttus` 필드 존재 확인, 값 semantics는 TO_VERIFY)
- [x] destination (`statnTid`/`statnTnm` 필드 존재, arrival 쪽과 consistency는 TO_VERIFY)
- [ ] express/local
- [x] source timestamp (`recptnDt`/`lastRecptnDt`, D-016)

### Join experiment

Arrival ↔ Position:

- [x] train number exact match rate — **핵심 spike, 광범위하게 측정** (D-017/020/023/026/032/033/034 — Line1 91.7%, Line3 100%, Line2는 station code에 따라 54.5%~100% 혼재, 원인 일부 미상)
- [x] line+direction consistency — 방향 가설은 기각됨 (D-027, 매칭/미매칭 그룹 모두에 양방향 혼재)
- [ ] destination consistency — TO_VERIFY
- [ ] time tolerance

---

## F. Subway Actual Ground Truth

**Pass/Fail이 전체 프로젝트에 영향.**

후보 규칙을 실제 데이터에서 비교:

1. Position arrival state
2. Arrival API `arvlCd=1`
3. sequence-based interval
4. two-source corroboration

평가:

- [x] coverage — 역별로 측정 (시청 91.7%, 강남 station code별 54.5%~100%, 안국/교대/역삼 100% — `SUBWAY_ACTUAL_RULE_V0.md` 참고)
- [ ] interval width — 정성적으로만 확인(수 poll 단위), 히스토그램 등 정량 집계는 미착수
- [x] contradictions — 이번 세션 샘플에서 역행/모순 전이 미관측
- [x] false repeats — 이번 세션 샘플에서 미관측
- [x] train ID instability — 시청 train 5166 케이스 문서화 (position에 전혀 안 잡힘, 원인 미상)
- [x] line-specific failure — 강남 `1002000201`의 미해결 갭 문서화 (D-026/D-032/D-033)

결과는 `SUBWAY_ACTUAL_RULE_V0.md`로 기록하고 rule version을 부여. **완료 — v0, 상태 CONDITIONAL** (`../data-contract/SUBWAY_ACTUAL_RULE_V0.md`)

---

## G. Mixed Transit Route

Official: https://www.data.go.kr/data/15000414/openapi.do

### 테스트

- [x] 서울 내 좌표 A/B (D-024, D-030 — 삼청동↔역삼역 확정)
- [x] bus+subway mixed route 반환 (D-029 — 4개 후보 corridor 전부 `railLinkList` 채워진 mixed leg 확인)
- [x] alternative routes (D-024 — 서울역↔강남역 20개, D-030 — 삼청동↔역삼역 24개)
- [x] bus route id (`routeId`, D-024)
- [x] bus stop id (`fid`/`tid`, D-024/D-034)
- [x] subway line/station id (`routeNm`="3호선" 등 + `fid`/`tid`, D-034)
- [ ] walking/transfer time — 별도 필드로 명시 확인 안 됨
- [x] total time (`time` 필드, D-030/D-031 — 50분)
- [x] ID를 realtime APIs와 join — **조사 완료, 결과가 API 종류별로 다름**: bus는 `routeId`가 `getArrInfoByRouteAll`/`getBusPosByRouteSt`의 `busRouteId`/`routeId`와 **직접 일치** (D-038, crosswalk 불필요), subway는 `fid`/`tid`가 realtime `statnId`와 **다른 ID 공간**이라 직접 조인 불가 (D-034, crosswalk 필요)

### 판정

- GO: route candidate provider로 사용
- **CONDITIONAL: crosswalk 필요 ← 현재 판정 (D-034)**
- PIVOT: fixed corridor / static route input

---

## H. Bus Route / Station Master

Route: https://www.data.go.kr/data/15000193/openapi.do  
Station: https://www.data.go.kr/data/15000303/openapi.do

- [x] route id (`busRouteId`, D-011 — 753 → `100100118`)
- [ ] stop order
- [ ] stop id
- [ ] section id
- [ ] coordinates
- [ ] direction/turnaround

Master snapshot을 날짜/version과 함께 보존.

---

## I. Historical Bus Section

Official: https://data.seoul.go.kr/dataList/OA-21217/A/1/datasetView.do

**DROPPED (D-025/D-028)** — 실시간 폴링용 OpenAPI가 아니라 주/월 단위
대용량 ZIP 다운로드 방식이고, data.seoul.go.kr 페이지에 서비스 종료
안내가 있어 PM이 baseline 후보에서 드롭 결정. 아래 항목은 API 호출로
검증할 대상이 아니므로 미체크 상태로 둔다.

- [ ] 최근 데이터 파일/OpenAPI sample 확보
- [ ] 날짜
- [ ] hour bucket
- [ ] route
- [ ] from/to stop
- [ ] avg travel time
- [ ] realtime master와 join rate

**성공 시** PRE_TRIP bus prior 후보.

---

## J. Subway Alert

Official: https://data.seoul.go.kr/dataList/OA-22718/A/1/datasetView.do

- [ ] 현재 incident 조회
- [ ] line/station mapping 가능 여부
- [ ] start/end time
- [ ] type/category

MVP에서는 "현재 이미 발생 중인 사건"만 context로 반영.

---

# Spike 결과 공통 템플릿

```markdown
## API

### Verdict
PASS / CONDITIONAL / FAIL

### Tested at
...

### Calls
...

### Observed schema
...

### Identity
...

### Timestamp semantics
...

### Quality
- success
- empty
- duplicate
- business error

### Rate limit implication
...

### Main Use Case mapping
어떤 probability variable / state에 쓰이는가?

### Risks
...

### Next decision
...
```
