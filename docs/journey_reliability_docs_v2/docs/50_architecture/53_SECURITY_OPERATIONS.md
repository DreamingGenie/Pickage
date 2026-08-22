---
doc_id: JR-DOC-053
title: Security and Operations
version: 1.0
status: REVIEW
owner: Infra/Backend
last_updated: 2026-08-22
depends_on:
  - JR-DOC-022
  - JR-DOC-052
source_of_truth_for:
  - secret-policy
  - privacy-policy
  - runbook-requirements
  - external-api-operations
supersedes: []
---

# Security & Operations

## 1. Secret Inventory

```text
SEOUL_OPEN_API_KEY
SEOUL_SUBWAY_REALTIME_KEY
DATA_GO_BUS_API_KEY
TMAP_APP_KEY
```

Kakao key는 blocked source로 기본 runtime dependency 아님.

## 2. Secret Rules

금지:
- git commit
- frontend bundle
- README 실제값
- CI console full print
- exception body에 credential 포함
- multi-key rotation으로 provider quota 우회

허용:
- local `.env.local` gitignore
- GitLab CI/CD Variables
- Jenkins Credentials
- EC2 environment/secret store

## 3. GitLab / Jenkins

- protected branch deploy credential 최소권한
- secret masking
- production-like environment variable는 CI에서 주입
- fork/MR pipeline에 protected secret 노출 금지
- secret scan step 권장

## 4. Transport

배포:
- HTTPS
- internal service는 보안그룹으로 필요한 port만
- public Kafka/Flink UI 노출 금지 또는 접근 제한

## 5. CORS

Web origin allow-list.
`*` + credential 조합 금지.

정확 domain은 deploy URL 확정 후 기록.

## 6. Logging

로그 금지:
- API key
- complete auth headers
- exact user origin coordinate를 기본 access log field로 저장
- raw provider payload 전체를 application log로 반복 출력

Raw storage는 controlled data artifact와 log를 구분한다.

## 7. User Data Minimization

Minimum Release는 account가 없다.

Journey request에 필요한:
- origin
- destination
- target

은 runtime 계산에 사용할 수 있지만 analytics event에는 exact coordinate를 기본 저장하지 않는다.

Demo/test 사용자 입력은 public sample coordinate 또는 명시적 test fixture를 우선.

## 8. Journey Persistence

목표:
- active state와 result snapshot 최소 저장
- 불필요 장기 개인 이동 history를 만들지 않음

정확 Journey TTL은 Release 전 확정.

### Resolution Gate
G5 Security Review.

TTL을 근거 없이 24h/30d로 임의 결정하지 않는다.

## 9. Share Privacy

Share payload:
- destination label
- target time
- expected arrival summary
- probability
- calculated_at

제외:
- exact origin
- exact GPS trace
- provider raw ID
- Evidence debug
- secret

Token:
- opaque unpredictable random
- expiration 필수
- exact TTL TBD at G5

## 10. External API Quota

각 collector:
- expected daily call count 계산
- **공유 credential 단위 total call budget** 계산
- current quota 기록
- retry가 quota 폭증하지 않게 exponential backoff/jitter
- provider quota/business error를 HTTP transport success와 별도 계측
- error storm circuit-break 후보

Phase 1에서 5개 realtime subway poller가 15 s cadence로 shared 1,000/day quota를 실제 소진했다(`EVD-OPS-001`).
팀원 key rotation으로 한도 우회하지 않고 shared rate budget 또는 공식 quota 증액을 사용한다.

## 11. Provider Failure

### Route Provider
새 analysis 불가.
기존 Journey live probability를 route topology 없이 새로 만들지 않음.

### Realtime Bus/Subway
마지막 success가 stale threshold 이내인지 확인.
stale이면 UI state 전달.

### TMAP
WALK query failure:
- 이미 검증/저장된 route point를 fallback으로 쓸지 여부는 environment-specific policy 필요
- 실제 runtime에서 임의 직선거리/속도 대체 금지 unless explicit fallback decision

## 12. Backup

백업 대상:
- Decision/Evidence docs(repo)
- raw evidence/object storage
- canonical schema/migration
- Journey DB 필요 시
- distribution artifacts

API cache는 재생성 가능하면 primary backup 대상 아님.

## 13. Restore

Final 전 최소:
- DB restore 또는 clean bootstrap
- MinIO/object artifact access
- service restart
- latest distribution reload

검증.

## 14. Rollback

release artifact/version을 식별 가능하게 유지.

Probability engine/model:
- artifact version
- rule version
- code version

rollback 시 결과 provenance가 남아야 한다.

## 15. Monitoring

Minimum dashboard/summary:
- collector last success/error
- Kafka lag
- Flink checkpoint/state
- API p95/error
- distribution artifact age
- disk/object usage
- external provider error

threshold는 profile 후 설정.

## 16. Demo Preflight

시연 전 확인:
- provider keys loaded
- route provider reachable
- bus/subway collector healthy
- latest distribution artifact exists
- Journey API health
- Web reachable
- share optional
- fallback/demo evidence package available

provider outage 시 fake live result로 전환하지 않는다.
