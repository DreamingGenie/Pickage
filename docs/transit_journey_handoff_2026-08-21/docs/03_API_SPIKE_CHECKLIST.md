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

- [ ] route-wide endpoint 실제 명칭
- [ ] `busRouteId`
- [ ] `stId`, `staOrd`
- [ ] `vehId1`, `vehId2`
- [ ] `exps1`, `exps2`
- [ ] `mkTm`
- [ ] first/second bus semantics
- [ ] same source timestamp repeated responses
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

- [ ] 실제 endpoint 명 (`getBusPosByRtid` vs `...List` 문서 혼재)
- [ ] `vehId`
- [ ] `plainNo`
- [ ] `sectOrd`
- [ ] `sectionId`
- [ ] `stopFlag`
- [ ] `nextStId`
- [ ] `nextStTm` 실제 포함 여부
- [ ] `dataTm`
- [ ] `rtDist`, distance fields
- [ ] congestion/full-related fields 실제 제공/semantics
- [ ] turnaround/up-down 판정 필드

### 핵심 테스트

Arrival `vehId1/2`와 Position `vehId` 집합 일치율.

---

## C. Bus Actual / Residual

### Actual rule 후보

`stopFlag=0 → stopFlag=1` + target stop/section transition.

반드시 interval로 보존.

- [ ] lower/upper source time
- [ ] interval width
- [ ] impossible transitions
- [ ] same vehicle trip boundary

### Residual

`Actual - Predicted`

- [ ] lower/mid/upper residual
- [ ] lead time
- [ ] event weighting issue (prediction snapshot 많은 actual event가 전체를 지배하지 않도록 주의)

---

## D. Subway Arrival

Official: https://data.seoul.go.kr/dataList/OA-15799/A/1/datasetView.do

Sample service documented by Seoul:

`realtimeStationArrival/ALL`

### 후보 필드

- [ ] `subwayId`
- [ ] `updnLine`
- [ ] `statnId`
- [ ] `statnNm`
- [ ] `barvlDt`
- [ ] `btrainNo`
- [ ] `btrainSttus`
- [ ] `bstatnId`, `bstatnNm`
- [ ] `recptnDt`
- [ ] `arvlMsg2`
- [ ] `arvlCd`
- [ ] `lstcarAt`

### 품질

- [ ] 동일 `recptnDt` 반복
- [ ] train number 누락
- [ ] 역/호선별 item density
- [ ] barvlDt negative/zero/unexpected
- [ ] API latency

---

## E. Subway Position

Official: https://data.seoul.go.kr/dataList/OA-12601/A/1/datasetView.do

### 반드시 실제 response로 확인

- [ ] train number field
- [ ] line field
- [ ] direction
- [ ] station/current position
- [ ] train status sequence
- [ ] destination
- [ ] express/local
- [ ] source timestamp

### Join experiment

Arrival ↔ Position:

- [ ] train number exact match rate
- [ ] line+direction consistency
- [ ] destination consistency
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

- [ ] coverage
- [ ] interval width
- [ ] contradictions
- [ ] false repeats
- [ ] train ID instability
- [ ] line-specific failure

결과는 `SUBWAY_ACTUAL_RULE_V0.md`로 기록하고 rule version을 부여.

---

## G. Mixed Transit Route

Official: https://www.data.go.kr/data/15000414/openapi.do

### 테스트

- [ ] 서울 내 좌표 A/B
- [ ] bus+subway mixed route 반환
- [ ] alternative routes
- [ ] bus route id
- [ ] bus stop id
- [ ] subway line/station id
- [ ] walking/transfer time
- [ ] total time
- [ ] ID를 realtime APIs와 join

### 판정

- GO: route candidate provider로 사용
- CONDITIONAL: crosswalk 필요
- PIVOT: fixed corridor / static route input

---

## H. Bus Route / Station Master

Route: https://www.data.go.kr/data/15000193/openapi.do  
Station: https://www.data.go.kr/data/15000303/openapi.do

- [ ] route id
- [ ] stop order
- [ ] stop id
- [ ] section id
- [ ] coordinates
- [ ] direction/turnaround

Master snapshot을 날짜/version과 함께 보존.

---

## I. Historical Bus Section

Official: https://data.seoul.go.kr/dataList/OA-21217/A/1/datasetView.do

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
