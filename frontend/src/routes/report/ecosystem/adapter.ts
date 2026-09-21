import type {
  DependentsTrendResponse,
  DownloadsTrendResponse,
  PackagesOverviewResponse,
  TrendSeries,
  VersionShareResponse,
} from '@/api/types'
import type { ChartSeries } from '@/components/charts/geometry'
import type { ShareGroup } from '@/components/charts/version-share'
import {
  ALL_MAJORS,
  type EcosystemModel,
  type MajorSelection,
  type MajorSeries,
  type PackageCardModel,
} from '@/routes/report/ecosystem/model'

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

/**
 * 서버가 준 추이를 화면 시리즈로 옮긴다.
 *
 * <p>`tone` 은 **개요가 세운 순서**(= 카드 순서)에서 가져온다. 응답이 준 순서를 그대로
 * 쓰면 안 된다 — downloads 와 dependents 는 서로 다른 엔드포인트라 순서가 같다는 보장이
 * 없고, 그러면 같은 패키지가 두 차트에서 다른 선으로 그려진다.
 */
function toChartSeries(series: TrendSeries[], toneOf: Map<string, number>): ChartSeries[] {
  return series.map((s, i) => ({
    key: s.name,
    label: s.name,
    tone: toneOf.get(s.name) ?? i,
    // 서버는 결측 스냅샷의 행을 아예 보내지 않는다. 없는 점을 만들어 끼우지 않는다.
    points: s.points.map((p) => ({ t: p.snapshot_at, v: p.value })),
  }))
}

/**
 * §5 — major 별로 갈라져 온 dependents 를 패키지별로 다시 묶는다.
 *
 * 서버가 **숫자로 세워** 보낸 순서를 그대로 지킨다. 여기서 다시 정렬하면
 * `'1' < '10' < '2'` 를 피하려고 SQL 에 넣은 규칙이 무의미해진다.
 *
 * `major` 가 없는 시리즈는 **쪼갤 행이 없는 패키지**다(스냅샷 미수신). 이름은 존재하므로
 * 빈 목록으로 남기고 `not_found` 와 섞지 않는다.
 */
function groupByPackage(series: TrendSeries[]): Map<string, MajorSeries[]> {
  const byName = new Map<string, MajorSeries[]>()
  for (const s of series) {
    const list = byName.get(s.name) ?? []
    if (s.major !== undefined) {
      list.push({
        major: s.major,
        points: s.points.map((p) => ({ t: p.snapshot_at, v: p.value })),
      })
    }
    byName.set(s.name, list)
  }
  return byName
}

/**
 * major 들을 날짜별로 더해 `TOTAL` 선을 만든다.
 *
 * **없는 날짜를 0 으로 채우지 않는다.** major 마다 시작이 다르므로(아직 나오지 않은 버전은
 * 앞쪽이 잘려 있다) 실제로 관측된 날짜의 합집합만 쓴다. 그 날짜에 없는 major 는 그때
 * 0 이었던 것이 맞고, 더해도 값이 변하지 않는다.
 */
export function totalOf(majors: MajorSeries[]): { t: string; v: number }[] {
  const sum = new Map<string, number>()
  for (const m of majors) {
    for (const p of m.points) sum.set(p.t, (sum.get(p.t) ?? 0) + p.v)
  }
  return [...sum.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([t, v]) => ({ t, v }))
}

/**
 * 카드 하나의 Dependents 선. **고른 major 들을 합한 하나의 선이다**(구상안 §5.2).
 *
 * 아무것도 안 골랐으면 전부 합한다. 선 개수는 언제나 패키지당 하나라, 버전을 만져도
 * 위쪽 비교 차트의 선 수와 색 규칙이 흔들리지 않는다.
 *
 * 고른 major 가 그 패키지에 없으면 그냥 빠진다 — 지어내지 않는다. 선택기가 있는 것만
 * 보여주므로 정상 경로에서는 생기지 않지만, 저장된 선택이 되살아나는 경우에 대비한다.
 */
export function dependentsLineOf(
  name: string,
  majors: MajorSeries[],
  selected: MajorSelection,
  /** 선 모양 자리. 카드와 같은 번호를 줘야 범례·차트·카드가 어긋나지 않는다 */
  tone?: number,
): ChartSeries {
  const picked = selected.length === 0 ? majors : majors.filter((m) => selected.includes(m.major))

  return {
    key: name,
    label: selected.length === 0 ? name : `${name} ${labelOf(selected, majors)}`,
    tone,
    points: totalOf(picked),
  }
}

/**
 * 범례에 적을 버전 표기. 둘까지는 그대로 적고 그 이상은 개수로 줄인다 —
 * `express 1.x+2.x+3.x+7.x+9.x` 는 범례에서 이름을 밀어내 어느 선인지 알 수 없게 만든다.
 */
function labelOf(selected: MajorSelection, majors: MajorSeries[]): string {
  // 고른 순서가 아니라 서버가 세워 보낸 순서로 적는다. 누른 순서대로면 같은 선택이
  // 눌린 차례에 따라 다르게 보인다.
  const ordered = majors.filter((m) => selected.includes(m.major)).map((m) => `${m.major}.x`)
  if (ordered.length === 0) return '자료 없음'
  return ordered.length <= 2 ? ordered.join('+') : `${ordered.length}개 버전`
}

/** 시리즈가 실제로 시작하는 날짜. 시리즈마다 다르면 가장 늦은 시작을 쓴다. */
function observedFromOf(series: ChartSeries[]): string | undefined {
  const starts = series.map((s) => s.points[0]?.t).filter((t): t is string => Boolean(t))
  return starts.length ? starts.reduce((a, b) => (a > b ? a : b)) : undefined
}

export interface Delta {
  value: number
  /** 증감을 낸 양 끝 스냅샷 날짜. */
  from: string
  to: string
}

/**
 * 구간 양 끝의 차이. 점이 둘 미만이면 증감을 말할 수 없다.
 *
 * 표시 버전을 바꾸면 화면 쪽에서도 이 값을 다시 세야 해서 밖으로 연다.
 * 두 곳에서 각자 빼면 언젠가 결측 처리가 갈린다.
 *
 * **부르는 쪽은 반드시 화면에 그린 것과 같은(windowed) 시리즈를 넘겨야 한다** — 창을
 * 씌우기 전 전체 시리즈로 부르면 카드의 증감이 차트에 보이는 구간과 다른 것을 가리킨다(311c).
 */
export function deltaOf(series: ChartSeries | undefined): Delta | null {
  const points = series?.points.filter((p) => p.v !== null) ?? []
  if (points.length < 2) return null
  const first = points[0]
  const last = points[points.length - 1]
  return { value: (last.v as number) - (first.v as number), from: first.t, to: last.t }
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
  /**
   * 추이 둘과 버전 분포는 **없을 수 있다.** 각자 별도 호출이라 아직 안 왔거나 실패했을
   * 수 있고, 그때도 개요가 있으면 패키지 카드와 나머지 지표는 떠야 한다.
   *
   * 개요만 필수다 — 카드 자체를 만들 수 없기 때문이다.
   */
  downloads?: DownloadsTrendResponse
  dependents?: DependentsTrendResponse
  versionShare?: VersionShareResponse
}

export function toEcosystemModel({
  overview,
  downloads,
  dependents,
  versionShare,
}: EcosystemSources): EcosystemModel {
  /* 선 모양의 기준 순서. 개요가 세운 차례가 곧 카드 차례이고 기준 패키지가 0 번이다 */
  const toneOf = new Map(overview.items.map((item, i) => [item.name, i]))
  const downloadsSeries = toChartSeries(downloads?.series ?? [], toneOf)

  // §5 — dependents 는 major 별로 온다. 화면이 고른 버전에 따라 선을 만들 수 있도록
  // 쪼개진 채로 들고 있고, 기본값(TOTAL)만 미리 합쳐 둔다.
  const majorsByName = groupByPackage(dependents?.series ?? [])
  const dependentsSeries = overview.items.map((item, i) =>
    dependentsLineOf(item.name, majorsByName.get(item.name) ?? [], ALL_MAJORS, i),
  )
  const dependentsByName = new Map(dependentsSeries.map((s) => [s.key, s]))

  const shareByName = new Map((versionShare?.items ?? []).map((i) => [i.name, i.slices]))

  const packages: PackageCardModel[] = overview.items.map((item) => {
    const delta = deltaOf(dependentsByName.get(item.name))
    return {
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
      dependentsDelta: delta?.value ?? null,
      dependentsDeltaFrom: delta?.from ?? null,
      dependentsDeltaTo: delta?.to ?? null,
      // §6 — 이 응답 전체의 기준일. 패키지마다 갈리지 않는다(요청 하나에 스냅샷 하나).
      versionShareSnapshotAt: versionShare?.snapshot_at ?? null,
      // 구상안 §5.2 `availableDisplayVersions`. 자료가 있는 major 만 고를 수 있다.
      availableMajors: (majorsByName.get(item.name) ?? []).map((m) => m.major),
    }
  })

  /**
   * 0.2 — 세 응답이 각자 `not_found` 를 준다. 같은 이름이 여러 번 나오므로 합집합을 만든다.
   * 하나라도 못 찾았으면 그 이름은 화면에서 빠진 것이 맞다.
   */
  const notFound = [
    ...new Set([
      ...overview.not_found,
      ...(downloads?.not_found ?? []),
      ...(dependents?.not_found ?? []),
    ]),
  ]

  return {
    snapshotAt: overview.snapshot_at,
    packages,
    series: { downloads: downloadsSeries, dependents: dependentsSeries },
    dependentsByMajor: Object.fromEntries(majorsByName),
    notFound,
    observedFrom: {
      downloads: observedFromOf(downloadsSeries),
      dependents: observedFromOf(dependentsSeries),
    },
  }
}
