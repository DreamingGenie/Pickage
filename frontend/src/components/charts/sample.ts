import {
  ALL_SNAPSHOTS,
  BY_NAME,
  LATEST_SNAPSHOT,
  dependentsByMajor,
  pointMetric,
  seriesOf,
  type MockPackage,
} from '@/api/mock/dataset'
import type {
  DependentsTrendResponse,
  DownloadsTrendResponse,
  PackagesOverviewResponse,
  TrendSeries,
  VersionShareResponse,
} from '@/api/types'
import { toEcosystemModel } from '@/routes/report/ecosystem/adapter'
import type { EcosystemModel } from '@/routes/report/ecosystem/model'

/**
 * 인트로 미리보기용 예시.
 *
 * 값은 지어낸 것이고 화면에 "예시"로 표시한다. 다만 **mock 응답을 그대로 통과시켜**
 * 만든다 — 예시 전용 모델을 손으로 짜 두면 화면이 실제 API 로는 못 만드는 모양을
 * 그리게 되고, 그 사실이 서버를 붙일 때가 되어서야 드러난다.
 *
 * 미리보기라 서버 왕복이 없어야 하므로 `mock/handlers` 의 비동기 함수 대신
 * 같은 데이터에서 응답 객체를 동기로 만든다.
 */

const PREVIEW_NAMES = ['winston', 'pino', 'bunyan']
const PREVIEW_WEEKS = 78

const found = PREVIEW_NAMES.map((n) => BY_NAME.get(n)).filter((p): p is MockPackage => Boolean(p))

const from = ALL_SNAPSHOTS[Math.max(0, ALL_SNAPSHOTS.length - PREVIEW_WEEKS)]
const last = ALL_SNAPSHOTS.length - 1

const inWindow = (p: { snapshot_at: string }) => p.snapshot_at >= from

const overview: PackagesOverviewResponse = {
  snapshot_at: LATEST_SNAPSHOT,
  items: found.map((pkg) => {
    const stars = pointMetric(pkg, 'stars', last)
    const prevStars = pointMetric(pkg, 'stars', last - 1)
    const issues = pointMetric(pkg, 'open_issues', last)
    const prevIssues = pointMetric(pkg, 'open_issues', last - 1)
    return {
      name: pkg.name,
      repo_url: pkg.repo_url,
      latest_version: pkg.latest_version,
      published_at: pkg.published_at,
      description: pkg.description,
      licenses: pkg.licenses,
      is_deprecated: pkg.is_deprecated,
      downloads: seriesOf(pkg, 'downloads').at(-1)?.value ?? null,
      stars,
      stars_delta: stars !== null && prevStars !== null ? stars - prevStars : null,
      open_issues: issues,
      open_issues_delta: issues !== null && prevIssues !== null ? issues - prevIssues : null,
    }
  }),
  not_found: [],
}

const downloads: DownloadsTrendResponse = {
  metric: 'downloads',
  unit: 'weekly',
  series: found.map((pkg) => ({
    name: pkg.name,
    points: seriesOf(pkg, 'downloads').filter(inWindow),
  })),
  not_found: [],
}

/**
 * §5 — dependents 는 major 별로 갈라져 나간다(mock/handlers.ts 의 `buildDependentsSeries` 와
 * 같은 규칙). 여기서 `major` 없이 하나로만 냈더니 `adapter.ts`의 `groupByPackage`가
 * "major 없는 시리즈는 쪼갤 행이 없는 패키지"로 보고 통째로 버려, 미리보기의 Dependents
 * 카드가 항상 빈 상태로 떴다.
 */
const dependents: DependentsTrendResponse = {
  metric: 'dependents',
  sum_over_versions: true,
  series: found.flatMap((pkg): TrendSeries[] => {
    const split = dependentsByMajor(pkg)
      .map((r) => ({ name: pkg.name, major: r.major, points: r.points.filter(inWindow) }))
      .filter((r) => r.points.length > 0)
    return split.length > 0 ? split : [{ name: pkg.name, points: [] }]
  }),
  not_found: [],
}

const versionShare: VersionShareResponse = {
  snapshot_at: LATEST_SNAPSHOT,
  basis: 'dependents',
  sum_over_versions: true,
  items: found.map((pkg) => {
    const total = pkg.majors.reduce((sum, m) => sum + m.dependents, 0)
    return {
      name: pkg.name,
      slices: [...pkg.majors]
        .sort((a, b) => b.dependents - a.dependents)
        .map((m) => ({
          major: m.major,
          dependents: m.dependents,
          pct: total === 0 ? 0 : Math.round((1000 * m.dependents) / total) / 10,
        })),
    }
  }),
  not_found: [],
}

export const SAMPLE_ECOSYSTEM: EcosystemModel = toEcosystemModel({
  overview,
  downloads,
  dependents,
  versionShare,
})
