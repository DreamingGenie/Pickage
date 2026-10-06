import type { RemovalReasonsResponse } from '@/api/types'
import {
  EMPTY_REMOVAL_REASONS_MODEL,
  type PackageRemovalReasons,
  type RemovalCounts,
  type RemovalReasonsModel,
} from '@/routes/report/ecosystem/removal-reasons-model'

/**
 * wire → view-model. `res` 가 아직 없으면(쿼리 대기 중) 빈 모델을 돌려준다 —
 * `transitions-adapter` 와 같은 약속이다.
 *
 * `packages` 의 순서는 서버 응답 순서가 아니라 **비교 순서(`requestedNames`)** 를 따른다.
 * 위 칩 줄·차트가 그 순서로 색을 정해 두었으므로 여기서도 맞춰야 같은 패키지가
 * 어디서나 같은 색으로 보인다.
 */
export function toRemovalReasonsModel(
  res: RemovalReasonsResponse | undefined,
  requestedNames: readonly string[],
): RemovalReasonsModel {
  if (!res) return EMPTY_REMOVAL_REASONS_MODEL

  const byName = new Map<string, RemovalReasonsResponse['series'][number]>()
  for (const item of res.series) byName.set(item.name, item)

  const packages: PackageRemovalReasons[] = requestedNames
    .filter((name) => byName.has(name))
    .map((name) => {
      const item = byName.get(name)!
      return {
        key: name,
        unit: item.unit,
        dataStatus: item.data_status,
        counts: countsOf(item),
      }
    })

  return {
    period: res.period,
    t1: res.t1 ?? null,
    t2: res.t2 ?? null,
    population: res.series[0]?.population ?? null,
    packages,
    notFound: res.not_found,
  }
}

/**
 * COMPLETE·NO_DATA 만 값을 채운다. 계약상 그 둘이면 네 필드가 모두 실수치여야 하므로,
 * 하나라도 `null` 이면 **0 으로 메우지 않고** 행 전체를 "모른다" 로 떨어뜨린다.
 */
function countsOf(item: RemovalReasonsResponse['series'][number]): RemovalCounts | null {
  if (item.data_status !== 'COMPLETE' && item.data_status !== 'NO_DATA') return null
  if (
    item.removals === null ||
    item.no_replacement === null ||
    item.with_replacement === null ||
    item.dependents === null
  ) {
    return null
  }
  return {
    removals: item.removals,
    noReplacement: item.no_replacement,
    withReplacement: item.with_replacement,
    dependents: item.dependents,
  }
}
