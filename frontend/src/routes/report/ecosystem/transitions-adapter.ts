import type { TransitionsResponse } from '@/api/types'
import {
  EMPTY_TRANSITIONS_MODEL,
  type PackageTransitions,
  type TransitionCounts,
  type TransitionRow,
  type TransitionsModel,
  type UnobservedFreshness,
} from '@/routes/report/ecosystem/transitions-model'

/**
 * wire → view-model. `res`가 아직 없으면(쿼리 대기 중) 빈 모델을 돌려준다 —
 * 호출부가 undefined 분기를 따로 두지 않아도 되게 한다.
 *
 * `packages`의 순서는 서버 응답 순서가 아니라 **비교 순서(`requestedNames`)**를 따른다 —
 * 칩 줄·차트가 이미 그 순서로 색·모양을 정해 뒀으므로, 여기서도 맞춰야 같은 패키지가
 * 어디서나 같은 순서로 보인다.
 */
export function toTransitionsModel(
  res: TransitionsResponse | undefined,
  requestedNames: readonly string[],
): TransitionsModel {
  if (!res) return EMPTY_TRANSITIONS_MODEL

  const byName = new Map<string, TransitionRow[]>()
  for (const item of res.series) {
    const rows = byName.get(item.name) ?? []
    rows.push({
      kind: item.kind,
      dataStatus: item.data_status,
      counts: countsOf(item),
    })
    byName.set(item.name, rows)
  }

  const packages: PackageTransitions[] = requestedNames
    .filter((name) => byName.has(name))
    .map((name) => ({ key: name, rows: byName.get(name) ?? [] }))

  return {
    period: res.period,
    t1: res.t1 ?? null,
    t2: res.t2 ?? null,
    // 행마다 실려 오지만 지금은 전부 같은 값이다 — 첫 행에서 대표로 하나만 뽑는다.
    population: res.series[0]?.population ?? null,
    packages,
    notFound: res.not_found,
  }
}

/**
 * COMPLETE·NO_DATA 만 값을 채운다. **`inflow_adopted`는 서버 계산값을 그대로 쓴다** —
 * `inflow - inflow_new`를 여기서 다시 구하지 않는다. 재계산은 서버와 클라가 언젠가
 * 다른 값을 낼 위험만 만든다.
 */
function countsOf(item: TransitionsResponse['series'][number]): TransitionCounts | null {
  if (item.data_status !== 'COMPLETE' && item.data_status !== 'NO_DATA') return null
  if (
    item.retained === null ||
    item.outflow === null ||
    item.unobserved === null ||
    item.inflow === null ||
    item.inflow_new === null ||
    item.inflow_adopted === null
  ) {
    // 계약상 COMPLETE·NO_DATA 면 여섯 필드 모두 값이 있어야 한다. 어긋나면 화면이
    // 조용히 0으로 메우지 않고 "모른다"로 보이게 null 취급한다.
    return null
  }
  return {
    retained: item.retained,
    outflow: item.outflow,
    unobserved: item.unobserved,
    inflowAdopted: item.inflow_adopted,
    inflowRaw: item.inflow,
    inflowNew: item.inflow_new,
    unobservedFreshness: freshnessOf(item),
  }
}

/**
 * 관측불가 분해 (S15P21A506-421). **`null` 을 0 으로 바꾸지 않는다** — 셋이 없는 것은
 * "방치된 의존자가 0명" 이 아니라 "아직 모른다" 다. 서버가 세 값을 싣기 시작한 것은
 * 마이그레이션 배포보다 나중이라, 그 사이 회차에는 `COMPLETE` 인데 셋만 없는 행이 있다.
 *
 * 합이 `unobserved` 와 어긋나면 그리지 않는다. 서버에 DB CHECK 가 있으므로 정상 경로에서는
 * 일어나지 않고, 일어났다면 열 짝이 밀린 것이라 **그 상태로 그리는 그림이 곧 거짓**이다.
 */
function freshnessOf(item: TransitionsResponse['series'][number]): UnobservedFreshness | null {
  const { unobserved_recent: recent, unobserved_stale: stale, unobserved_dormant: dormant } = item
  if (recent === null || stale === null || dormant === null) return null
  if (item.unobserved !== recent + stale + dormant) return null
  return { recent, stale, dormant }
}
