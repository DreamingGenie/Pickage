# EVD-ACCESS-001 — Demo ACCESS_WALK

**Status: VERIFIED**

## Claim under test

Demo origin coordinate `126.9809, 37.5825` → Route A first boarding stop
춘추문 (mixed stop ID `100000417`, route raw coordinate
`126.97965309715137, 37.58308213227146`) is a computable point-to-point
walking leg via TMAP's pedestrian routing API.

## What was done

Live call to `POST https://apis.openapi.sk.com/tmap/routes/pedestrian`
with `startX/startY` = demo origin, `endX/endY` = 춘추문 raw coordinate,
using the real `TMAP_APP_KEY`. Executed 2026-08-22 03:37 UTC.

## Result

- HTTP 200
- `totalDistance` = **297 m**
- `totalTime` = **245 s** (~4 min 5 s)
- 9 GeoJSON features returned (turn-by-turn geometry + 2 point markers)

## Coordinate roles

| Point | Role | Source |
|---|---|---|
| Start | `ORIGIN_POINT` | Demo OD definition (`10_SERVICE_PLAN.md`) |
| End | `BUS_STOP` | Phase 0 packaged mixed-route Raw (`fid=100000417`) |

## Limitation

- Single point-estimate call (TMAP `totalTime` is not a distribution — see
  Source Register §4). No repeated-call variance was collected for this
  leg in Phase 1 (out of scope per the execution contract — ACCESS_WALK
  variance work was not requested).
- Time-of-day/weather sensitivity of the 245 s estimate is unverified.

## Artifact

- `raw/access_walk_demo_origin_to_chunchumun.json` — Bronze-contract
  sample (sha256 hash embedded in file), collector `spike-v0`.

## Reproduction

```bash
cd docs/journey_reliability_docs_v2/baseline/phase0/scripts/spikes
python tmap_walk_spike.py 126.9809 37.5825 126.97965309715137 37.58308213227146 \
  "demo_origin_ORIGIN_POINT" "춘추문_100000417_BUS_STOP"
```
