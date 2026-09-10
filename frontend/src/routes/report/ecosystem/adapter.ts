import type {
  DependentsTrendResponse,
  DownloadsTrendResponse,
  PackagesOverviewResponse,
  TrendSeries,
  VersionShareResponse,
} from '@/api/types'
import type { ChartSeries } from '@/components/charts/geometry'
import type { ShareGroup } from '@/components/charts/version-share'
import type { EcosystemModel, PackageCardModel } from '@/routes/report/ecosystem/model'

/**
 * 서버 응답 → 화면 뷰 모델.
 *
 * 이름 바꾸기 말고 실제로 하는 일이 셋 있다.
 * 1. **major 접기** — 조각이 많으면 상위 5개 + 기타로 접는다(명세 §6 화면 연결).
 * 2. **구간 증감 계산** — Dependents 순증감은 서버가 주지 않는다. 받은 시리즈의
 *    양 끝 차이로 만든다. 그래서 조회 기간을 바꾸면 이 값도 같이 바뀐다.
 * 3. **결측 보존** — 없는 관측을 0 으로 채우지 않는다.
 */

/** §6 — 조각이 이보다 많으면 나머지를 "기타"로 접는다. */
const MAX_SLICES = 5

/** 접힌 나머지 조각의 라벨. */
export const OTHER_MAJOR = '기타'

function toChartSeries(series: TrendSeries[]): ChartSeries[] {
  return series.map((s) => ({
    key: s.name,
    label: s.name,
    // 서버는 결측 스냅샷의 행을 아예 보내지 않는다. 없는 점을 만들어 끼우지 않는다.
    points: s.points.map((p) => ({ t: p.snapshot_at, v: p.value })),
  }))
}

/** 시리즈가 실제로 시작하는 날짜. 시리즈마다 다르면 가장 늦은 시작을 쓴다. */
function observedFromOf(series: ChartSeries[]): string | undefined {
  const starts = series.map((s) => s.points[0]?.t).filter((t): t is string => Boolean(t))
  return starts.length ? starts.reduce((a, b) => (a > b ? a : b)) : undefined
}

/** 구간 양 끝의 차이. 점이 둘 미만이면 증감을 말할 수 없다. */
function deltaOf(series: ChartSeries | undefined): number | null {
  const points = series?.points.filter((p) => p.v !== null) ?? []
  if (points.length < 2) return null
  return (points[points.length - 1].v as number) - (points[0].v as number)
}

/**
 * §6 화면 연결 — major 조각 접기.
 *
 * `pct` 는 서버가 준 값을 그대로 더한다. 다시 계산하지 않는다 —
 * 같은 비율을 두 곳에서 구하면 언젠가 서로 다른 숫자가 나온다(0.7).
 */
export function foldSlices(slices: VersionShareResponse['items'][number]['slices']): ShareGroup[] {
  if (slices.length === 0) return []

  // 서버가 dependents 내림차순으로 보내지만, 접기 기준이 순서에 의존하므로 확실히 해 둔다.
  const sorted = [...slices].sort((a, b) => b.dependents - a.dependents)
  const head = sorted.slice(0, MAX_SLICES)
  const tail = sorted.slice(MAX_SLICES)

  const groups: ShareGroup[] = head.map((s) => ({
    // "4" 가 아니라 "4.x" 로 적는다. 정확한 버전으로 오해되지 않게.
    label: `${s.major}.x`,
    share: s.pct / 100,
  }))

  if (tail.length > 0) {
    groups.push({
      label: OTHER_MAJOR,
      share: tail.reduce((sum, s) => sum + s.pct, 0) / 100,
    })
  }
  return groups
}

export interface EcosystemSources {
  overview: PackagesOverviewResponse
  downloads: DownloadsTrendResponse
  dependents: DependentsTrendResponse
  /** §6 은 별도 호출이고 실패해도 나머지가 떠야 하므로 없을 수 있다. */
  versionShare?: VersionShareResponse
}

export function toEcosystemModel({
  overview,
  downloads,
  dependents,
  versionShare,
}: EcosystemSources): EcosystemModel {
  const downloadsSeries = toChartSeries(downloads.series)
  const dependentsSeries = toChartSeries(dependents.series)

  const dependentsByName = new Map(dependentsSeries.map((s) => [s.key, s]))
  const shareByName = new Map((versionShare?.items ?? []).map((i) => [i.name, i.slices]))

  const packages: PackageCardModel[] = overview.items.map((item) => ({
    key: item.name,
    repoUrl: item.repo_url,
    latestVersion: item.latest_version,
    publishedAt: item.published_at,
    description: item.description,
    licenses: item.licenses,
    isDeprecated: item.is_deprecated,
    downloads: item.downloads,
    stars: item.stars,
    starsDelta: item.stars_delta,
    openIssues: item.open_issues,
    openIssuesDelta: item.open_issues_delta,
    versionShare: foldSlices(shareByName.get(item.name) ?? []),
    dependentsDelta: deltaOf(dependentsByName.get(item.name)),
  }))

  /**
   * 0.2 — 세 응답이 각자 `not_found` 를 준다. 같은 이름이 여러 번 나오므로 합집합을 만든다.
   * 하나라도 못 찾았으면 그 이름은 화면에서 빠진 것이 맞다.
   */
  const notFound = [
    ...new Set([...overview.not_found, ...downloads.not_found, ...dependents.not_found]),
  ]

  return {
    snapshotAt: overview.snapshot_at,
    packages,
    series: { downloads: downloadsSeries, dependents: dependentsSeries },
    notFound,
    observedFrom: {
      downloads: observedFromOf(downloadsSeries),
      dependents: observedFromOf(dependentsSeries),
    },
  }
}
