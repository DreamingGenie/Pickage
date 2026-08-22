---
doc_id: JR-DOC-052
title: Internal API Contract
version: 1.1
status: REVIEW
owner: Backend/Full-stack
last_updated: 2026-08-22
depends_on:
  - JR-DOC-020
  - JR-DOC-040
  - JR-DOC-042
source_of_truth_for:
  - internal-http-api
supersedes: []
---

# Internal API Contract

> URL은 v1 제안. Request/Response semantics와 IDs가 정본이며 framework에 따라 path 변경 시 ADR/traceability 갱신.

## Common Envelope

Success:

```json
{
  "data": {},
  "meta": {
    "schemaVersion": "v1",
    "requestId": "...",
    "generatedAt": "..."
  }
}
```

Error:

```json
{
  "error": {
    "code": "UNSUPPORTED_ROUTE",
    "message": "...",
    "retryable": false
  },
  "meta": {
    "requestId": "..."
  }
}
```

실제 provider error body를 그대로 frontend에 노출하지 않는다.

---

# API-001 POST `/api/v1/route-candidates`

## Purpose
origin/destination의 structural route 후보 조회.

## Request

```json
{
  "origin": {"lat": 0.0, "lon": 0.0, "label": "..."},
  "destination": {"lat": 0.0, "lon": 0.0, "label": "..."}
}
```

## Response

```json
{
  "data": {
    "selectedCandidateId": "route_...",
    "candidates": [
      {
        "routeCandidateId": "route_...",
        "providerRank": 1,
        "selectionStatus": "SELECTED",
        "selectionReason": "PROVIDER_FIRST_SUPPORTED",
        "supportStatus": "SUPPORTED",
        "legs": []
      }
    ]
  }
}
```

Minimum Release frontend는 selected candidate 하나만 분석 UI에 사용.

## Errors
- `UNSUPPORTED_GEOGRAPHY`
- `ROUTE_NOT_FOUND`
- `ROUTE_PROVIDER_ERROR`
- `ROUTE_MAPPING_INCOMPLETE`

---

# API-002 POST `/api/v1/journeys/analyze`

## Request

```json
{
  "origin": {"lat": 0.0, "lon": 0.0, "label": "..."},
  "destination": {"lat": 0.0, "lon": 0.0, "label": "..."},
  "targetArrivalAt": "2026-08-22T09:30:00+09:00",
  "targetReliability": 0.90,
  "routeCandidateId": "route_..."
}
```

## Response

```json
{
  "data": {
    "journeyId": "journey_...",
    "resultVersion": 1,
    "routeCandidateId": "route_...",
    "p50ArrivalAt": null,
    "p90ArrivalAt": null,
    "onTimeProbability": null,
    "plannedConnectionSuccessProbability": null,
    "recommendedDeparture": {
      "status": "AVAILABLE|INSUFFICIENT_DATA|NOT_COMPUTED",
      "at": null,
      "targetReliability": 0.90,
      "scope": "SELECTED_ROUTE"
    },
    "confidence": {
      "label": "LOW",
      "validationScope": "COMPONENT_ONLY",
      "modelCoverage": "PARTIAL",
      "fallbacks": [],
      "limitations": [],
      "freshness": "FRESH"
    },
    "calculatedAt": "..."
  }
}
```

`null`을 fake value로 채우지 않는다.

## Errors
- `INSUFFICIENT_DATA`
- `UNSUPPORTED_ROUTE`
- `ANALYSIS_FAILED`
- `PROVIDER_ERROR`

---

# API-003 POST `/api/v1/journeys/{journeyId}/start`

분석 snapshot을 live Journey state로 시작.

Idempotent 가능해야 함.

---

# API-004 GET `/api/v1/journeys/{journeyId}`

현재:
- state
- active leg
- result snapshot
- freshness
- next candidate summary

반환.

---

# API-005 POST `/api/v1/journeys/{journeyId}/events`

## Request

```json
{
  "eventType": "BUS_SKIPPED",
  "occurredAt": "...",
  "targetServiceId": "...",
  "idempotencyKey": "client-generated-or-server-contract"
}
```

## Response
new state + new result snapshot.

## Error
- `EVENT_NOT_ALLOWED_IN_STATE`
- `EVENT_ALREADY_APPLIED`
- `TARGET_SERVICE_MISMATCH`
- `REFORECAST_FAILED`

같은 idempotency key 재시도는 double mutation 금지.

---

# API-006 GET `/api/v1/journeys/{journeyId}/evidence`

일반 user-friendly evidence summary.

Debug mode 권한/환경에서는:
- distribution version
- sample counts
- rule versions
- simulation run
- validation scope
- WAIT source/version
- coordinate role/source

추가 가능.

Raw secret/provider payload를 그대로 노출하지 않는다.

---

# API-007 POST `/api/v1/journeys/{journeyId}/share`

Share Snapshot 생성.

Response:
```json
{
  "data": {
    "shareToken": "...",
    "shareUrl": "...",
    "expiresAt": null
  }
}
```

`expiresAt` exact TTL은 Security Gate TBD.

---

# API-008 GET `/api/v1/share/{token}`

축약 result.

origin exact coordinate 제외.

---

# API-009 GET `/api/v1/health/summary`

운영/데모 preflight용.

포함 후보:
- collector health
- stream health
- distribution artifact latest
- provider reachability

secret/PII 노출 금지.

---

# Error Taxonomy

| Code | HTTP candidate | Retry |
|---|---:|---|
| INPUT_INVALID | 400 | N |
| UNSUPPORTED_GEOGRAPHY | 422 | N |
| ROUTE_NOT_FOUND | 404/422 | maybe |
| ROUTE_MAPPING_INCOMPLETE | 422 | N |
| INSUFFICIENT_DATA | 422 | later |
| PROVIDER_ERROR | 503 | Y |
| STALE_DATA | 409/503 or result-state | Y |
| EVENT_NOT_ALLOWED_IN_STATE | 409 | N |
| EVENT_ALREADY_APPLIED | 200/409 policy | N |
| INTERNAL_ERROR | 500 | maybe |

HTTP exact mapping은 backend convention freeze 시 확정.
Error code가 UI contract의 정본이다.

---

# Schema Version

모든 public response:
`schemaVersion`.

breaking change:
`/v2` 또는 explicit migration.

frontend/backend PR은 example fixture로 contract test.
