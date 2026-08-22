# EVD-DEST-001 — 역삼 2호선 endpoint → 멀티캠퍼스 역삼 FINAL_WALK

**Status: VERIFIED (as STATION_CENTER-based estimate — NOT an exit-based estimate)**

## Claim under test

역삼 2호선 endpoint → 멀티캠퍼스 역삼 (서울특별시 강남구 테헤란로 212)
is a computable point route/time via TMAP, with the start coordinate's
role explicitly recorded.

## What was done

1. **Geocoded the destination** via TMAP `fullAddrGeo`
   (`서울특별시 강남구 테헤란로 212`) — real live call, 2026-08-22 03:38 UTC.
2. **Ran TMAP pedestrian routing** from the 역삼역 mixed-route graph node
   (`fx,fy = 127.03649815857663,37.50063694862099`, `tid=02210`) to the
   geocoded destination's entrance point.

## Result — geocoding

- HTTP 200, `totalCount=1` (unambiguous match)
- Building point: `127.039589, 37.501276`
- Entrance point (`newLatEntr/newLonEntr`): `127.039533, 37.501331`
- Matched building name field confirms the "테헤란로 212" address, zipcode `06220`
- Used the **entrance point**, not the building centroid, as the FINAL_WALK endpoint.

## Result — pedestrian route

- HTTP 200
- `totalDistance` = **329 m**
- `totalTime` = **300 s** (5 min)

## Coordinate roles (per PD-028 requirement)

| Point | Role | Source | Note |
|---|---|---|---|
| Start (역삼역) | **`STATION_CENTER` candidate — NOT a confirmed `STATION_EXIT`** | mixed-route API graph node (`tid=02210`, from Phase 0 packaged Raw) | No exit-specific coordinate for this FINAL_WALK is documented anywhere in the product docs; the only exit-level coordinate we hold for 역삼역 is `역삼역6번출구` (`122000179`, from the unrelated Route B bus alight stop), and nothing ties that specific exit to this destination |
| End (멀티캠퍼스 역삼) | `POI` (entrance) | TMAP `fullAddrGeo`, `newLatEntr/newLonEntr` |

Per the execution contract: **this is explicitly reported as a
station-center result, not hidden as if it were an exit-based
estimate.** If the product later commits to a specific 역삼역 exit for
this FINAL_WALK, this number must be re-run from that exit's real
coordinate, not silently relabeled.

## Artifacts

- `raw/geocode_multicampus_yeoksam.json`
- `raw/final_walk_yeoksam_station_to_multicampus.json`

## Reproduction

```bash
cd docs/journey_reliability_docs_v2/baseline/phase0/scripts/spikes
python ../../../../../../evidence/phase1/_scripts/tmap_geocode.py "서울특별시 강남구 테헤란로 212"
python tmap_walk_spike.py 127.03649815857663 37.50063694862099 127.039533 37.501331 \
  "역삼역_mixed_node_STATION_CENTER_candidate" "멀티캠퍼스역삼_entrance_POI"
```
