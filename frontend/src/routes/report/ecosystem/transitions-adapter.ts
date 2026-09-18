import type { TransitionsResponse } from '@/api/types'
import {
  EMPTY_TRANSITIONS_MODEL,
  type PackageTransitions,
  type TransitionCounts,
  type TransitionRow,
  type TransitionsModel,
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
  }
}
