---
doc_id: JR-DOC-051
title: Streaming and Storage Contract
version: 1.0
status: REVIEW
owner: Infra/Data
last_updated: 2026-08-22
depends_on:
  - JR-DOC-040
  - JR-DOC-050
source_of_truth_for:
  - stream-topics
  - event-time
  - storage-layers
  - replay
supersedes: []
---

# Streaming / Storage Contract

## 1. Logical Topics

실제 naming은 repo convention에 맞게 조정 가능하지만 역할은 고정.

```text
transit.raw.bus.arrival
transit.raw.bus.position
transit.raw.subway.arrival
transit.raw.subway.position
transit.silver.bus.observation
transit.silver.subway.observation
transit.gold.actual_arrival
transit.gold.residual
transit.dlq
```

mixed-route/TMAP은 요청 기반 utility라 collector streaming topic이 필수는 아니다.

---

# 2. Key Strategy

## Bus raw/silver
Preferred:
`route_id + veh_id`

Arrival response에 여러 target stop prediction이 있으므로 실제 normalized event key에는 target node를 추가할 수 있다.

Final key는 state query와 partition skew profile 후 ADR.

## Subway
`subway_id + train_no`

station progression을 같은 train partition에 유지하기 위함.

Actual state 내부에 station key를 포함.

---

# 3. Phase 1 Measured Workload Snapshot

`EVD-VOLUME-001` session 기준:
- 1,930 raw samples
- 61.8 MB / 약 70분
- 약 53 MB/h observed evidence-session workload
- `getArrInfoByRouteAll`이 raw bytes 대부분을 차지

이는 **production traffic estimate가 아니라 Phase 1 polling cadence의 측정값**이다.
true source/collector lateness는 timestamp instrumentation 결함으로 아직 없다.

# 4. Partition Count

**TBD-after-profile**

먼저 측정:
- events/hour
- bytes/hour
- active keys
- max key rate
- state bytes/key
- replay target

임의로 3/6/12 partition을 선택하지 않는다.

---

# 5. Delivery Semantics

External API polling 자체는 end-to-end exactly-once가 아니다.

목표:

```text
collector: at-least-once safe
downstream: deterministic dedupe/idempotent
Flink state/sink: checkpoint-based consistent processing
```

“exactly once”라는 문구는 실제 source→sink proof가 있을 때만 사용한다.

---

# 6. Event Time

Primary:
`source_generated_at`

Fallback:
`received_at` only when source time unavailable + flag.

API별:
- bus arrival call-level mkTm
- bus position vehicle-level dataTm
- subway train-level recptnDt

하나의 global timestamp rule 금지.

---

# 7. Watermark / Allowed Lateness

**TBD-after-valid-timestamp-profile**

Phase 1 SpikeResult의 near-zero timestamp는 사용하지 않는다. `PD-037`을 만족하는 collector run에서 profile:
`received_at - source_generated_at`

provider별 p50/p95/p99와 out-of-order rate를 측정.

그 후:
- watermark
- allowed lateness
- state correction policy

를 ADR로 고정.

---

# 8. State TTL

TTL은 임의 시간으로 정하지 않는다.

derive from:
- maximum relevant lead-time
- route/train lifecycle
- polling jitter
- late-event profile
- safety grace

expired state가 unfinished Prediction을 버리는 영향도 측정한다.

---

# 9. Checkpoint

Interval/storage는 benchmark 후 결정.

Acceptance:
- TaskManager failure 후 state 복구
- duplicate/lost residual count
- recovery time

기록.

---

# 10. Bronze

경로 예시:

```text
bronze/provider=seoul_bus/api=arrival/date=YYYY-MM-DD/hour=HH/
bronze/provider=seoul_bus/api=position/date=.../
bronze/provider=seoul_subway/api=arrival/date=.../
bronze/provider=seoul_subway/api=position/date=.../
```

Raw file contains:
- request metadata
- HTTP
- body
- hash
- receive time

## Small-file policy

초기 collection file layout는 그대로 보존 가능.
Spark/Flink 분석 단계에서는 object count/task overhead를 profile하고 compaction.

compaction 전/후 raw logical count/hash manifest 유지.

---

# 11. Silver

Canonical normalized observation.

필수:
- schema_version
- canonical IDs
- source time
- receive time
- quality flags
- raw_ref

---

# 12. Gold

```text
actual_arrival_interval
residual_event
leg_travel_time
distribution_artifact
validation_result
journey_simulation_eval
```

Gold는 derivation version을 기록한다.

---

# 13. Parquet Partition

초기 후보:
`date/provider/api`

route/station를 partition column으로 바로 추가하지 않는다.
high-cardinality small-files 위험.

실제 query pattern/size profile 후 변경.

---

# 14. Replay Contract

Replay envelope:

```yaml
replay_id:
source_snapshot:
speed_multiplier:
original_event_time:
replay_event_time:
amplified: true|false
copies_per_event:
purpose: FUNCTIONAL | BENCHMARK | FAILURE
```

## Real Replay
원본 event sequence/interval 보존 또는 가속.

## Amplified Replay
같은 logical data를 복제해 throughput limit 측정.

**절대 금지**
amplified copy를 training sample count로 세기.

---

# 15. Benchmark Matrix

Stream:
- 1x
- 5x
- 20x

측정:
- events/s
- p50/p99 processing latency
- consumer lag
- checkpoint
- state size
- backpressure

Batch:
- 1/2/4 worker
- runtime
- worker participation
- shuffle read/write
- spill
- skew

---

# 16. Optimization Proof

최소 2개 A/B.

후보:
- partition strategy
- broadcast join
- repartition
- cache/persist
- file compaction
- AQE

실제 bottleneck 없는 optimization을 억지로 선택하지 않는다.

---

# 17. Correctness Manifest

각 run:
- input row/event count
- unique logical keys
- output row count
- deterministic checksum
- aggregate summary
- distribution summary

optimization before/after 비교.

float quantile은 exact binary equality가 부적절할 수 있으므로 허용 tolerance를 metric별 문서화.
