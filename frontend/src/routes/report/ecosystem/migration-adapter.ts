import type { MigrationPairsResponse, MigrationSeriesItem } from '@/api/types'
import {
  DEFAULT_KIND,
  EMPTY_MIGRATION_MODEL,
  type MigrationEvidence,
  type MigrationModel,
  type PackageMigration,
} from '@/routes/report/ecosystem/migration-model'

/**
 * wire → view-model. `res` 가 아직 없으면(쿼리 대기 중) 빈 모델을 돌려준다 —
 * `removal-reasons-adapter` 와 같은 약속이다.
 *
 * `packages` 의 순서는 서버 응답 순서가 아니라 **비교 순서(`requestedNames`)** 를 따른다.
 * 위 칩 줄·다른 패널이 그 순서로 색을 정해 두었으므로 여기서도 맞춰야 같은 패키지가
 * 어디서나 같은 색으로 보인다.
 */
export function toMigrationModel(
  res: MigrationPairsResponse | undefined,
  requestedNames: readonly string[],
): MigrationModel {
  if (!res) return EMPTY_MIGRATION_MODEL

  const byName = new Map<string, MigrationSeriesItem>()
  for (const item of res.series) byName.set(item.name, item)

  const packages: PackageMigration[] = requestedNames
    .filter((name) => byName.has(name))
    .map((name) => {
      const item = byName.get(name)!
      return {
        key: name,
        snapshotAt: item.snapshot_at,
        shareBasis: item.share_basis,
        dataStatus: item.data_status,
        destinations: item.destinations.map((d) => ({
          name: d.name,
          sharePmPct: d.share_pm_pct,
          votes: d.votes,
          publisherMonths: d.publisher_months,
          evidence: evidenceOf(d.evidence),
          variant: d.variant,
          firstSeen: d.first_seen,
          lastSeen: d.last_seen,
        })),
        etc: item.etc
          ? {
              pairs: item.etc.pairs,
              sharePmPct: item.etc.share_pm_pct,
              belowFilter: item.etc.below_filter,
            }
          : null,
        observedPairs: item.observed_pairs,
      }
    })

  return {
    kind: res.kind ?? DEFAULT_KIND,
    packages,
    notFound: res.not_found,
  }
}

/**
 * 모르는 등급은 **가장 약한 쪽으로 떨어뜨린다.**
 *
 * 서버가 등급을 늘리면(빌더의 임계값이 바뀌면 그럴 수 있다) 화면이 모르는 문자열을 받는다.
 * 그때 `strict` 로 올리면 근거가 약한 이동에 "근거 강함" 배지가 붙는데, 그건 화면이
 * 사용자에게 없는 확신을 주는 방향이라 반대로 둔다. 배지가 한 단계 낮게 보이는 것은
 * 다음 배포에서 고치면 되지만, 잘못된 확신은 그 사이에 판단을 바꾼다.
 */
function evidenceOf(raw: string): MigrationEvidence {
  return raw === 'strict' || raw === 'recommended' ? raw : 'loose'
}
