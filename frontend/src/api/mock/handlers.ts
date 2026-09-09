/**
 * mock 엔드포인트 구현.
 *
 * 서버가 없는 동안 화면을 붙여보기 위한 것이다. **응답 모양뿐 아니라 규칙도** 흉내낸다 —
 * 검증 순서(V001 → V002 → V004), 중복 제거, 요청 순서 재배열, 부분 실패(`not_found`),
 * 지표 결측(null). 여기서 규칙을 대충 흉내내면 서버를 붙일 때 화면이 처음 보는
 * 응답을 만나게 되고, 그때는 원인이 화면인지 서버인지 가리기 어렵다.
 */

import { ApiError } from '@/api/client'
import {
  ALL_SNAPSHOTS,
  BY_NAME,
  LATEST_SNAPSHOT,
  MOCK_DICTIONARY,
  MOCK_PACKAGES,
  pointMetric,
  seriesOf,
  type MockPackage,
} from '@/api/mock/dataset'
import {
  DEFAULT_WEEKS,
  MAX_NAMES,
  MAX_WEEKS,
  NPM_NAME_RE,
  SEARCH_LIMIT_DEFAULT,
  SEARCH_LIMIT_MAX,
  type DependentsTrendResponse,
  type DictManifest,
  type DownloadsTrendResponse,
  type PackageDictionary,
  type PackageOverview,
  type PackageSearchResponse,
  type PackagesOverviewResponse,
  type TrendQuery,
  type TrendSeries,
  type VersionShareResponse,
} from '@/api/types'

/** 서버 왕복처럼 보이게 하는 지연. 로딩 상태가 실제로 화면에 뜨는지 확인하려면 필요하다. */
const LATENCY_MS = 220

const delay = <T>(value: T): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS))

const fail = (code: 'V001' | 'V002' | 'V003' | 'V004' | 'S001', message: string): never => {
  throw new ApiError(code === 'S001' ? 500 : 400, code, message)
}

/* ------------------------------------------------------------------ *
 * 공통 검증 (0.1 · 0.4)
 * ------------------------------------------------------------------ */

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

/**
 * `names` 검증. 순서는 명세의 에러 표를 따른다 —
 * 누락(V001) → 상한(V002) → 형식(V004). 중복은 서버가 제거한다.
 */
function normalizeNames(names: readonly string[] | undefined): string[] {
  const cleaned = (names ?? []).map((n) => n.trim()).filter(Boolean)
  if (cleaned.length === 0) fail('V001', '패키지명(names)은 필수입니다.')

  const unique = [...new Set(cleaned)]
  if (unique.length > MAX_NAMES) {
    fail('V002', `한 번에 최대 ${MAX_NAMES}개까지 조회할 수 있습니다.`)
  }
  for (const name of unique) {
    if (!NPM_NAME_RE.test(name)) fail('V004', '패키지명 형식이 올바르지 않습니다.')
  }
  return unique
}

function checkDate(value: string | undefined, label: string): string | undefined {
  if (value === undefined || value === '') return undefined
  if (!DATE_RE.test(value) || Number.isNaN(Date.parse(value))) {
    fail('V003', `${label} 형식이 올바르지 않습니다. (YYYY-MM-DD)`)
  }
  return value
}

/** 0.5 — 응답은 **요청한 이름 순서**로 정렬한다. DB 는 순서를 보장하지 않는다. */
function split(names: string[]): { found: MockPackage[]; not_found: string[] } {
  const found: MockPackage[] = []
  const not_found: string[] = []
  for (const name of names) {
    const pkg = BY_NAME.get(name)
    if (pkg) found.push(pkg)
    else not_found.push(name)
  }
  return { found, not_found }
}

/* ------------------------------------------------------------------ *
 * 2.2 사전
 * ------------------------------------------------------------------ */

/** 내용 해시 파일명(2.2). mock 이라 고정값이지만 경로 모양은 실제와 같게 둔다. */
const DICT_URL = '/static/dict/packages.a3f21c.json'

export function mockDictManifest(): Promise<DictManifest> {
  return delay<DictManifest>({
    url: DICT_URL,
    count: MOCK_DICTIONARY.length,
    built_at: LATEST_SNAPSHOT,
  })
}

export function mockDictionary(): Promise<PackageDictionary> {
  return delay([...MOCK_DICTIONARY])
}

/* ------------------------------------------------------------------ *
 * 2.4 GET /packages/search
 * ------------------------------------------------------------------ */

/**
 * 접두사 검색만 한다. 중간 일치는 v1 범위 밖이다(§2.4 범위 밖) —
 * mock 이 중간 일치를 지원하면 화면이 서버가 못 하는 동작에 기대게 된다.
 */
export function mockSearch(q: string | undefined, limit?: number): Promise<PackageSearchResponse> {
  const query = (q ?? '').trim()
  if (!query) fail('V001', '검색어(q)는 필수입니다.')
  if (limit !== undefined && limit > SEARCH_LIMIT_MAX) {
    fail('V002', `limit은 최대 ${SEARCH_LIMIT_MAX}까지 가능합니다.`)
  }
  if (query.length < 1) fail('V004', '검색어는 1자 이상이어야 합니다.')

  const take = limit ?? SEARCH_LIMIT_DEFAULT
  const lower = query.toLowerCase()

  // 사전과 같은 정렬(다운로드 내림차순)을 쓰므로 배열 순서가 곧 인기순이다.
  const items = MOCK_DICTIONARY.filter((name) => name.toLowerCase().startsWith(lower)).slice(
    0,
    take,
  )

  return delay<PackageSearchResponse>({ query, items })
}

/* ------------------------------------------------------------------ *
 * 3. GET /packages
 * ------------------------------------------------------------------ */

export function mockPackagesOverview(
  names: readonly string[] | undefined,
): Promise<PackagesOverviewResponse> {
  const list = normalizeNames(names)
  const { found, not_found } = split(list)
  const last = ALL_SNAPSHOTS.length - 1

  const items: PackageOverview[] = found.map((pkg) => {
    const downloads = seriesOf(pkg, 'downloads')
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
      // 0.5 — 스냅샷이 없으면 지표만 null 이다. 항목 자체는 응답에 들어간다.
      downloads: downloads.at(-1)?.value ?? null,
      stars,
      // 첫 스냅샷이라 직전 값이 없으면 delta 는 null 이다.
      stars_delta: stars !== null && prevStars !== null ? stars - prevStars : null,
      open_issues: issues,
      open_issues_delta: issues !== null && prevIssues !== null ? issues - prevIssues : null,
    }
  })

  return delay<PackagesOverviewResponse>({ snapshot_at: LATEST_SNAPSHOT, items, not_found })
}

/* ------------------------------------------------------------------ *
 * 4·5. 추이
 * ------------------------------------------------------------------ */

/** `from`·`to` 를 실제 스냅샷 축 위의 구간으로 바꾼다. 기간 상한도 여기서 본다. */
function resolveWindow(from?: string, to?: string): { from: string; to: string } {
  const checkedFrom = checkDate(from, '시작 날짜')
  const checkedTo = checkDate(to, '끝 날짜')

  const end = checkedTo ?? LATEST_SNAPSHOT
  const endIndex = ALL_SNAPSHOTS.indexOf(end)
  // 스냅샷 축에 없는 날짜도 형식만 맞으면 받는다. 잘라내기는 문자열 비교로 처리된다.
  const fallbackStart =
    ALL_SNAPSHOTS[
      Math.max(0, (endIndex < 0 ? ALL_SNAPSHOTS.length - 1 : endIndex) - (DEFAULT_WEEKS - 1))
    ]
  const start = checkedFrom ?? fallbackStart

  if (start > end) fail('V002', '시작 날짜가 끝 날짜보다 뒤입니다.')

  const weeks = Math.round((Date.parse(end) - Date.parse(start)) / (7 * 864e5)) + 1
  if (weeks > MAX_WEEKS) {
    fail('V002', `한 번에 최대 ${MAX_NAMES}개, 최대 ${MAX_WEEKS}주까지 조회할 수 있습니다.`)
  }
  return { from: start, to: end }
}

function buildSeries(
  found: MockPackage[],
  metric: 'downloads' | 'dependents',
  window: { from: string; to: string },
): TrendSeries[] {
  return found.map((pkg) => ({
    name: pkg.name,
    points: seriesOf(pkg, metric).filter(
      (p) => p.snapshot_at >= window.from && p.snapshot_at <= window.to,
    ),
  }))
}

export function mockDownloadsTrend({
  names,
  from,
  to,
}: Partial<TrendQuery>): Promise<DownloadsTrendResponse> {
  const list = normalizeNames(names)
  const window = resolveWindow(from, to)
  const { found, not_found } = split(list)

  return delay<DownloadsTrendResponse>({
    metric: 'downloads',
    unit: 'weekly',
    series: buildSeries(found, 'downloads', window),
    not_found,
  })
}

export function mockDependentsTrend({
  names,
  from,
  to,
}: Partial<TrendQuery>): Promise<DependentsTrendResponse> {
  const list = normalizeNames(names)
  const window = resolveWindow(from, to)
  const { found, not_found } = split(list)

  return delay<DependentsTrendResponse>({
    metric: 'dependents',
    sum_over_versions: true,
    series: buildSeries(found, 'dependents', window),
    not_found,
  })
}

/* ------------------------------------------------------------------ *
 * 6. GET /packages/version
 * ------------------------------------------------------------------ */

export function mockVersionShare(
  names: readonly string[] | undefined,
  snapshotAt?: string,
): Promise<VersionShareResponse> {
  const list = normalizeNames(names)
  const at = checkDate(snapshotAt, '기준 날짜') ?? LATEST_SNAPSHOT
  const { found, not_found } = split(list)

  // §6 — 형식은 맞으나 데이터가 없는 날짜는 에러가 아니다. 200 에 빈 slices 가 나간다.
  const known = ALL_SNAPSHOTS.includes(at)

  const items = found.map((pkg) => {
    if (!known || pkg.noSnapshot || pkg.majors.length === 0) {
      return { name: pkg.name, slices: [] }
    }
    const total = pkg.majors.reduce((sum, m) => sum + m.dependents, 0)
    const slices = [...pkg.majors]
      .sort((a, b) => b.dependents - a.dependents)
      .map((m) => ({
        major: m.major,
        dependents: m.dependents,
        // pct 는 **해당 패키지 안에서의** 비율이다. 패키지별로 각각 100% 가 된다.
        pct: total === 0 ? 0 : Math.round((1000 * m.dependents) / total) / 10,
      }))
    return { name: pkg.name, slices }
  })

  return delay<VersionShareResponse>({
    snapshot_at: at,
    basis: 'dependents',
    sum_over_versions: true,
    items,
    not_found,
  })
}

/** 화면 기본값·미리보기가 쓰는 이름. 카탈로그에서 가져와 오타로 어긋나지 않게 한다. */
export const DEFAULT_COMPARISON = MOCK_PACKAGES.slice(0, 3).map((p) => p.name)
