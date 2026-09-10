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
  ALL_PACKAGES,
  ALL_SNAPSHOTS,
  BY_NAME,
  LATEST_SNAPSHOT,
  MOCK_DICTIONARY,
  MOCK_PACKAGES,
  dependentsByMajor,
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
  SIMILAR_LIMIT_DEFAULT,
  SIMILAR_LIMIT_MAX,
  type DependentsTrendResponse,
  type DictManifest,
  type DownloadsTrendResponse,
  type PackageDictionary,
  type PackageOverview,
  type PackageSearchResponse,
  type PackagesOverviewResponse,
  type SimilarPackagesResponse,
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

const inWindow = (window: { from: string; to: string }) => (p: { snapshot_at: string }) =>
  p.snapshot_at >= window.from && p.snapshot_at <= window.to

function buildDownloadsSeries(
  found: MockPackage[],
  window: { from: string; to: string },
): TrendSeries[] {
  return found.map((pkg) => ({
    name: pkg.name,
    points: seriesOf(pkg, 'downloads').filter(inWindow(window)),
  }))
}

/**
 * §5 — dependents 는 **major 별로 갈라져 나간다.** 같은 이름이 여러 번 나온다.
 *
 * 쪼갤 행이 없는 패키지(스냅샷 미수신)는 서버와 같이 **`major` 없는 빈 시리즈 하나**로
 * 낸다. 빼버리면 화면이 그 이름을 못 찾은 것으로 오해한다.
 */
function buildDependentsSeries(
  found: MockPackage[],
  window: { from: string; to: string },
): TrendSeries[] {
  // 반환 타입을 못 박는다. 안 적으면 두 갈래(major 있는 것 · 없는 것)의 리터럴 타입이
  // 서로 다른 배열로 추론되어 `major` 가 필수인 쪽으로 좁혀진다.
  return found.flatMap((pkg): TrendSeries[] => {
    const split = dependentsByMajor(pkg)
      .map((r) => ({ name: pkg.name, major: r.major, points: r.points.filter(inWindow(window)) }))
      .filter((r) => r.points.length > 0)

    return split.length > 0 ? split : [{ name: pkg.name, points: [] }]
  })
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
    series: buildDownloadsSeries(found, window),
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
    series: buildDependentsSeries(found, window),
    not_found,
  })
}

/* ------------------------------------------------------------------ *
 * 기능-03 · UC4. GET /packages/similar
 * ------------------------------------------------------------------ */

/**
 * 유사 패키지.
 *
 * **후보 선정은 지어낸 것이다.** 시드(`seed_service_full.sql`)는 쓰임새별 묶음에서 후보를
 * 뽑지만 mock 데이터에는 쓰임새 정보가 없다. 그래서 이름에서 파생한 결정적 순서로 고른다 —
 * 목록의 *모양*(순위 연속·점수 내림차순·자기 자신 배제)만 서버와 같고, **어떤 패키지가
 * 후보인지는 뜻이 없다.**
 *
 * 난수를 쓰지 않는 것이 중요하다. 새로고침마다 후보가 바뀌면 화면 버그와 구분할 수 없다.
 */
export function mockSimilarPackages(
  name: string | undefined,
  limit: number | undefined,
): Promise<SimilarPackagesResponse> {
  const base = (name ?? '').trim()

  // 검증 순서는 서버와 같다 — 누락(V001) → 상한(V002) → 형식(V004).
  if (!base) fail('V001', '기준 패키지(name)는 필수입니다.')
  if (limit !== undefined && limit > SIMILAR_LIMIT_MAX) {
    fail('V002', `limit은 최대 ${SIMILAR_LIMIT_MAX}까지 가능합니다.`)
  }
  if (limit !== undefined && limit < 1) fail('V004', 'limit은 1 이상이어야 합니다.')
  if (!NPM_NAME_RE.test(base)) fail('V004', `패키지 이름 형식이 올바르지 않습니다: ${base}`)

  const pkg = BY_NAME.get(base)
  if (!pkg) {
    return delay<SimilarPackagesResponse>({
      base,
      data_status: 'NO_DATA',
      candidates: [],
      not_found: [base],
    })
  }

  const take = limit ?? SIMILAR_LIMIT_DEFAULT
  const candidates = ALL_PACKAGES.filter((p) => p.name !== base)
    // 기준 이름을 섞어 정렬한다. 안 섞으면 모든 패키지가 같은 후보 목록을 갖는다.
    .map((p) => ({ p, order: fnv(base + ' ' + p.name) }))
    .sort((a, b) => a.order - b.order)
    .slice(0, take)
    .map(({ p }, i) => ({
      rank: i + 1,
      // 시드와 같은 식. 순위가 내려갈수록 점수가 낮아진다.
      score: Math.round((0.94 - (i + 1) * 0.035) * 1000) / 1000,
      name: p.name,
      latest_version: p.latest_version,
      description: p.description,
    }))

  return delay<SimilarPackagesResponse>({
    base,
    model_ver: 'mock-v1-20260831',
    data_status: 'COMPLETE',
    candidates,
    not_found: [],
  })
}

/** FNV-1a. `Math.imul` 로 32비트를 유지해 환경이 달라도 같은 값이 나온다. */
function fnv(s: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
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
