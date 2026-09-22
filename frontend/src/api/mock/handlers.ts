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
  MOCK_REMOVAL_REASONS,
  MOCK_TRANSITIONS,
  TRANSITION_PERIOD_SCALE,
  dependentsByMajor,
  pointMetric,
  seriesOf,
  type MockPackage,
} from '@/api/mock/dataset'
import {
  MAX_NAMES,
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
  type PdfGenerateRequest,
  type PdfJob,
  type RemovalReasonsResponse,
  type RemovalReasonsSeriesItem,
  type SimilarPackagesResponse,
  type TransitionPeriodParam,
  type TransitionSeriesItem,
  type TransitionsResponse,
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

/**
 * `from`·`to` 를 실제 스냅샷 축 위의 구간으로 바꾼다.
 *
 * **생략하면 보유한 전부다** — `from` 은 최초 스냅샷, `to` 는 최신 스냅샷이다. 기간 상한은
 * 없다(S15P21A506-374). 서버의 `SnapshotWindow.of` 와 같은 규칙이어야 mock 으로 본 화면이
 * 실서버에서 달라지지 않는다.
 */
function resolveWindow(from?: string, to?: string): { from: string; to: string } {
  const checkedFrom = checkDate(from, '시작 날짜')
  const checkedTo = checkDate(to, '끝 날짜')

  // 스냅샷 축에 없는 날짜도 형식만 맞으면 받는다. 잘라내기는 문자열 비교로 처리된다.
  const end = checkedTo ?? LATEST_SNAPSHOT
  const start = checkedFrom ?? ALL_SNAPSHOTS[0]

  if (start > end) fail('V002', '시작 날짜가 끝 날짜보다 뒤입니다.')

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
 * 기능-14. 보고서 PDF
 * ------------------------------------------------------------------ */

/**
 * mock 보고서.
 *
 * **PDF 바이트는 만들지 않는다.** 브라우저에서 PDF 를 조립하려면 라이브러리가 하나 더
 * 필요하고, 그렇게 만든 문서는 서버가 만드는 것과 모양이 달라 비교에도 못 쓴다.
 * 그래서 mock 은 <b>생성·미리보기까지</b>만 흉내내고 다운로드는 실서버에서만 된다.
 *
 * 화면이 그 사실을 알 필요는 없다 — 다운로드는 주소를 여는 일이라 mock 분기가 없고,
 * mock 으로 돌리는 동안 그 버튼을 누르면 서버가 없다는 것이 그대로 드러난다.
 */
const mockPdfHtml = new Map<string, string>()

export function mockGeneratePdf(request: PdfGenerateRequest): Promise<PdfJob> {
  const list = normalizeNames(request.names)
  const { found, not_found } = split(list)
  if (found.length === 0) {
    fail('V001', '보고서를 만들 수 있는 패키지가 없습니다. 이름을 확인해 주세요.')
  }

  const names = found.map((p) => p.name)
  const sections = request.sections ?? []
  const id = `mock-${names.join('-')}-${sections.join('-')}`

  // 서버와 같은 규칙(구상안 §13.6). 스코프 문자는 파일명에 남기지 않는다.
  const fileName = `Pickage_${names.join('-').replace(/[^A-Za-z0-9._-]/g, '-')}_${LATEST_SNAPSHOT}.pdf`

  mockPdfHtml.set(id, mockReportHtml(names, sections, not_found))

  return delay<PdfJob>({
    report_id: id,
    status: 'COMPLETE',
    file_name: fileName,
    // 실제 크기가 아니다. 화면이 "크기 표시" 자리를 그리는지 보기 위한 값이다.
    bytes: 12_000 + names.length * 3_400,
    created_at: new Date().toISOString(),
    // 커뮤니티 분석은 이제 기능이 있어 실린다(mock 은 자리 문구만). 기능 심화 분석만 자리와 사유가 실린다.
    omitted: sections.filter((s) => s !== 'COMMUNITY'),
  })
}

export function mockPdfPreview(reportId: string): Promise<string> {
  const html = mockPdfHtml.get(reportId)
  if (!html) fail('S001', '보고서가 만료되었습니다. 다시 만들어 주세요.')
  return delay(html as string)
}

/** 서버 렌더러의 모양만 흉내낸다. 값은 지어낸 것이다. */
function mockReportHtml(names: string[], sections: readonly string[], notFound: string[]): string {
  const rows = names
    .map((name) => {
      const pkg = BY_NAME.get(name)
      return (
        `<tr><td>${name}</td><td>${pkg?.latest_version ?? '-'}</td>` +
        `<td class="n">${(pkg?.downloads ?? 0).toLocaleString()}</td></tr>`
      )
    })
    .join('')

  const pending = sections
    .map(
      (s) =>
        `<h2>${s === 'COMMUNITY' ? '커뮤니티 분석' : '기능 심화 분석'}</h2>` +
        (s === 'COMMUNITY'
          ? `<p class="note">mock 예시입니다. 실제 문서에는 기준 패키지의 저장소 수치·핵심 논의·실제 논의 흐름이 실립니다.</p>`
          : `<p class="note">이 구역은 아직 제공되지 않습니다.</p>`),
    )
    .join('')

  return `<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"/>
<title>Pickage 생태계 보고서</title>
<style>
body{font-family:'Pretendard','Malgun Gothic',sans-serif;font-size:11pt;line-height:1.6;color:#111827}
h1{font-size:20pt;margin:0 0 4px}
h2{font-size:13pt;margin:22px 0 8px;padding-bottom:4px;border-bottom:1px solid #d1d5db}
table{width:100%;border-collapse:collapse;margin:6px 0 12px}
th,td{border:1px solid #e5e7eb;padding:6px 8px;text-align:left}
.n{text-align:right}
.note{font-size:9pt;color:#4b5563}
</style></head><body>
<h1>Pickage 생태계 보고서</h1>
<p>${names.join(' · ')}</p>
<p class="note">mock 응답입니다. 값은 지어낸 것이고 모양만 서버와 같습니다.</p>
<h2>비교 대상</h2>
<table><thead><tr><th>패키지</th><th>최신 버전</th><th class="n">주간 다운로드</th></tr></thead>
<tbody>${rows}</tbody></table>
${notFound.length ? `<p class="note">찾지 못한 패키지: ${notFound.join(', ')}</p>` : ''}
${pending}
<h2>자료 상태와 해석 한계</h2>
<p class="note">의존 수는 버전별 합계라 실제 사용처 수보다 큽니다.</p>
</body></html>`
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

/* ------------------------------------------------------------------ *
 * S15P21A506-361·391. GET /packages/transitions
 * ------------------------------------------------------------------ */

const TRANSITION_PERIODS: readonly TransitionPeriodParam[] = ['1y', '3y', '5y']

function checkPeriod(period: string | undefined): TransitionPeriodParam {
  if (period === undefined || period === '') return '3y'
  if (!TRANSITION_PERIODS.includes(period as TransitionPeriodParam)) {
    fail('V004', `period는 ${TRANSITION_PERIODS.join(', ')} 중 하나여야 합니다: ${period}`)
  }
  return period as TransitionPeriodParam
}

/** `LATEST_SNAPSHOT` 에서 period 만큼 거꾸로 뺀 날짜. 서버는 표에 저장된 값을 그대로
 *  돌려줄 뿐 계산하지 않지만(TransitionPeriod.java), mock 은 보여줄 표가 없어 계산해 맞춘다. */
function t1For(period: TransitionPeriodParam): string {
  const years = { '1y': 1, '3y': 3, '5y': 5 }[period]
  const d = new Date(`${LATEST_SNAPSHOT}T00:00:00Z`)
  d.setUTCFullYear(d.getUTCFullYear() - years)
  return d.toISOString().slice(0, 10)
}

function transitionRowsOf(name: string, period: TransitionPeriodParam): TransitionSeriesItem[] {
  const fixture = MOCK_TRANSITIONS[name]
  if (!fixture) {
    // 카탈로그에는 있지만(그래서 not_found 는 아님) 전환 픽스처가 없는 채움 패키지 —
    // 서버라면 배치가 아직 안 돈 패키지와 같은 모양이라 NOT_COMPUTED 로 낸다.
    return (['regular', 'peer', 'optional'] as const).map((kind) => ({
      name,
      kind,
      population: 'npm_all',
      retained: null,
      inflow: null,
      inflow_new: null,
      inflow_adopted: null,
      outflow: null,
      unobserved: null,
      unobserved_recent: null,
      unobserved_stale: null,
      unobserved_dormant: null,
      data_status: 'NOT_COMPUTED',
    }))
  }

  const scale = TRANSITION_PERIOD_SCALE[period]
  return fixture.map((row): TransitionSeriesItem => {
    if (!row.counts) {
      return {
        name,
        kind: row.kind,
        population: 'npm_all',
        retained: null,
        inflow: null,
        inflow_new: null,
        inflow_adopted: null,
        outflow: null,
        unobserved: null,
        unobserved_recent: null,
        unobserved_stale: null,
        unobserved_dormant: null,
        data_status: row.dataStatus,
      }
    }
    const retained = Math.round(row.counts.retained * scale)
    const inflow = Math.round(row.counts.inflow * scale)
    const inflowNew = Math.round(row.counts.inflowNew * scale)
    const outflow = Math.round(row.counts.outflow * scale)
    const unobserved = Math.round(row.counts.unobserved * scale)
    return {
      name,
      kind: row.kind,
      population: 'npm_all',
      retained,
      inflow,
      inflow_new: inflowNew,
      // 서버와 같은 계산(= inflow - inflow_new), 여기서 재발명하지 않는다.
      inflow_adopted: inflow - inflowNew,
      outflow,
      unobserved,
      ...freshnessOf(unobserved, period, row.freshnessMissing),
      data_status: row.dataStatus,
    }
  })
}

/**
 * 관측불가 분해 (S15P21A506-421). 구간마다 **정의상 비는 칸이 다르다** — 관측불가는 그
 * 구간 안에 대표 릴리스가 없다는 뜻이므로, 3년으로 보면 `recent`(3년 안)가 나올 수 없고
 * 5년으로 보면 `dormant` 만 남는다. mock 이 이 규칙을 어기면 화면이 실제로는 볼 수 없는
 * 모양을 연습하게 된다.
 *
 * 비율은 2026-09-21 운영 실측에서 가져왔다(1y recent 34.3% · stale 24.2%, 3y stale 36.8%).
 * **`dormant` 는 나머지로 구한다** — 반올림 때문에 셋의 합이 `unobserved` 에서 1 벌어지면
 * 서버 DB CHECK 를 어기는 응답이 되고, 화면 어댑터가 합을 다시 세어 분해를 버린다.
 */
const FRESHNESS_SPLIT: Record<TransitionPeriodParam, { recent: number; stale: number }> = {
  '1y': { recent: 0.343, stale: 0.242 },
  '3y': { recent: 0, stale: 0.368 },
  '5y': { recent: 0, stale: 0 },
}

function freshnessOf(
  unobserved: number,
  period: TransitionPeriodParam,
  missing?: true,
): Pick<TransitionSeriesItem, 'unobserved_recent' | 'unobserved_stale' | 'unobserved_dormant'> {
  // 마이그레이션 배포 ~ 재적재 사이의 행. COMPLETE 인데 분해만 없다.
  if (missing) {
    return { unobserved_recent: null, unobserved_stale: null, unobserved_dormant: null }
  }
  const split = FRESHNESS_SPLIT[period]
  const recent = Math.round(unobserved * split.recent)
  const stale = Math.round(unobserved * split.stale)
  return {
    unobserved_recent: recent,
    unobserved_stale: stale,
    unobserved_dormant: unobserved - recent - stale,
  }
}

export function mockTransitions(
  names: readonly string[] | undefined,
  period?: string,
): Promise<TransitionsResponse> {
  const list = normalizeNames(names)
  const resolvedPeriod = checkPeriod(period)
  const { found, not_found } = split(list)

  const series = found.flatMap((pkg) => transitionRowsOf(pkg.name, resolvedPeriod))

  // 서버 규칙: 응답의 모든 행이 NOT_COMPUTED 일 때만 t1·t2 키 자체가 없다.
  // (`hasAnyTransition()` 이 전체 표를 보고 판단 — 특정 period 만 비어도 다른 패키지에
  // 값이 있으면 그 값은 그대로 나간다. mock 도 같은 기준으로 판정한다.)
  const allNotComputed = series.length > 0 && series.every((s) => s.data_status === 'NOT_COMPUTED')

  return delay<TransitionsResponse>({
    metric: 'dependent_transitions',
    period: resolvedPeriod,
    ...(allNotComputed ? {} : { t1: t1For(resolvedPeriod), t2: LATEST_SNAPSHOT }),
    series,
    not_found,
  })
}

/* ------------------------------------------------------------------ *
 * GET /packages/removal-reasons  (S15P21A506-396·410)
 *
 * 위 transitions 와 **같은 프리셋·같은 기준일**을 쓴다(checkPeriod·t1For 재사용) —
 * 서버가 두 표에서 같은 t1·t2 를 꺼내므로 mock 도 같은 자리에서 만든다.
 * 단위만 다르다: 패키지 수가 아니라 전이 건수다.
 * ------------------------------------------------------------------ */

function removalRowOf(name: string, period: TransitionPeriodParam): RemovalReasonsSeriesItem {
  const fixture = MOCK_REMOVAL_REASONS[name]
  const base = { name, population: 'npm_all' as const, unit: 'transitions' }

  // 카탈로그에는 있지만 픽스처가 없는 채움 패키지 — 배치가 아직 안 돈 것과 같은 모양이다.
  if (!fixture || !fixture.counts) {
    return {
      ...base,
      removals: null,
      no_replacement: null,
      with_replacement: null,
      dependents: null,
      data_status: fixture?.dataStatus ?? 'NOT_COMPUTED',
    }
  }

  // **두 값을 먼저 스케일하고 더해서 removals 를 만든다.** removals 를 따로 스케일하면
  // 반올림 때문에 no + with != removals 가 되어 서버의 DB CHECK 를 어기는 응답이 된다.
  const scale = TRANSITION_PERIOD_SCALE[period]
  const noRepl = Math.round(fixture.counts.noReplacement * scale)
  const withRepl = Math.round(fixture.counts.withReplacement * scale)
  const removals = noRepl + withRepl
  // dependents <= removals 도 서버 CHECK 다. 스케일 뒤에도 지켜지게 자른다.
  const dependents = Math.min(Math.round(fixture.counts.dependents * scale), removals)

  return {
    ...base,
    removals,
    no_replacement: noRepl,
    with_replacement: withRepl,
    dependents,
    data_status: fixture.dataStatus,
  }
}

export function mockRemovalReasons(
  names: readonly string[] | undefined,
  period?: string,
): Promise<RemovalReasonsResponse> {
  const list = normalizeNames(names)
  const resolvedPeriod = checkPeriod(period)
  const { found, not_found } = split(list)

  const series = found.map((pkg) => removalRowOf(pkg.name, resolvedPeriod))
  const allNotComputed = series.length > 0 && series.every((s) => s.data_status === 'NOT_COMPUTED')

  return delay<RemovalReasonsResponse>({
    metric: 'removal_reasons',
    period: resolvedPeriod,
    ...(allNotComputed ? {} : { t1: t1For(resolvedPeriod), t2: LATEST_SNAPSHOT }),
    series,
    not_found,
  })
}

/** 화면 기본값·미리보기가 쓰는 이름. 카탈로그에서 가져와 오타로 어긋나지 않게 한다. */
export const DEFAULT_COMPARISON = MOCK_PACKAGES.slice(0, 3).map((p) => p.name)
