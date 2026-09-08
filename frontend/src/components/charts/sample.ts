import type { ChartSeries, TimePoint } from '@/components/charts/geometry'
import type { EcosystemModel } from '@/routes/report/ecosystem/model'

/**
 * 인트로 · 03A 미리보기용 예시.
 *
 * 값은 지어낸 것이고 화면에 "예시"로 표시한다.
 * 구조는 실제 수집 계획을 따른다 —
 *   Dependents · Version Share : NPMRequirements + PackageVersions 재계산
 *   Downloads                  : npm 공식 API, MVP 최대 18개월
 *   Stars · Issues             : Projects 스냅샷, 관측 시작 2022-05-08
 */

export const OBSERVED_FROM_PROJECTS = '2022-05-08'

const WEEK = 7 * 864e5
const END = '2026-08-31'

/** 결정적 난수. 새로고침마다 그래프가 흔들리지 않게 한다. */
const wobble = (seed: number, i: number) =>
  Math.sin((i + seed) / 3.3) * 0.55 + Math.sin((i + seed) / 8.7) * 0.9

function weekly(weeks: number, fn: (i: number) => number | null): TimePoint[] {
  const end = Date.parse(END)
  return Array.from({ length: weeks }, (_, i) => ({
    t: new Date(end - (weeks - 1 - i) * WEEK).toISOString().slice(0, 10),
    v: fn(i),
  }))
}

const dependents: ChartSeries[] = [
  {
    key: 'winston',
    label: 'winston',
    points: weekly(104, (i) => Math.round(11200 + i * 13 + wobble(1, i) * 180)),
  },
  {
    key: 'pino',
    label: 'pino',
    points: weekly(104, (i) => Math.round(2900 + i * 26 + wobble(7, i) * 120)),
  },
  {
    key: 'bunyan',
    label: 'bunyan',
    points: weekly(104, (i) => Math.round(1980 - i * 4.1 + wobble(13, i) * 60)),
  },
]

const downloads: ChartSeries[] = [
  {
    key: 'winston',
    label: 'winston',
    points: weekly(78, (i) => Math.round((12.1 + i * 0.021 + wobble(3, i) * 0.32) * 1e6)),
  },
  {
    key: 'pino',
    label: 'pino',
    points: weekly(78, (i) => Math.round((4.4 + i * 0.032 + wobble(9, i) * 0.22) * 1e6)),
  },
  {
    key: 'bunyan',
    label: 'bunyan',
    points: weekly(78, (i) => Math.round((0.72 - i * 0.0016 + wobble(17, i) * 0.05) * 1e6)),
  },
]

const first = (s: ChartSeries) => s.points.find((p) => p.v !== null)?.v ?? 0
const last = (s: ChartSeries) => [...s.points].reverse().find((p) => p.v !== null)?.v ?? 0

export const SAMPLE_ECOSYSTEM: EcosystemModel = {
  period: { from: dependents[0].points[0].t, to: END },
  observedFrom: {},
  coverageNote: {
    downloads: 'npm 공식 Downloads 자료는 최대 18개월까지만 제공됩니다',
    dependents: '수집된 구간을 넘습니다',
  },
  series: { dependents, downloads },
  packages: [
    {
      key: 'winston',
      availableDisplayVersions: ['TOTAL', '3.19.0', '3.18.3'],
      selectedDisplayVersion: 'TOTAL',
      versionShare: [
        { label: '3.x', share: 0.54 },
        { label: '2.x', share: 0.31 },
        { label: '1.x', share: 0.12 },
        { label: 'UNRESOLVED', share: 0.03 },
      ],
      stars: 22412,
      starsDelta52w: 574,
      recentIssues12w: 34,
      repositoryScope: 'PACKAGE_SCOPED',
      deprecatedLatest: false,
      deprecationObservedAt: '2026-08-31',
      dependentsDelta: Math.round(last(dependents[0]) - first(dependents[0])),
    },
    {
      key: 'pino',
      availableDisplayVersions: ['TOTAL', '10.3.1', '10.2.0'],
      selectedDisplayVersion: 'TOTAL',
      versionShare: [
        { label: '10.x', share: 0.41 },
        { label: '9.x', share: 0.36 },
        { label: '8.x', share: 0.19 },
        { label: 'UNRESOLVED', share: 0.04 },
      ],
      stars: 15038,
      starsDelta52w: 902,
      recentIssues12w: 21,
      repositoryScope: 'REPOSITORY_WIDE',
      deprecatedLatest: false,
      deprecationObservedAt: '2026-08-31',
      dependentsDelta: Math.round(last(dependents[1]) - first(dependents[1])),
    },
    {
      key: 'bunyan',
      availableDisplayVersions: ['TOTAL', '1.8.15'],
      selectedDisplayVersion: 'TOTAL',
      versionShare: [
        { label: '1.x', share: 0.88 },
        { label: '0.x', share: 0.05 },
        { label: 'UNRESOLVED', share: 0.07 },
      ],
      stars: 7192,
      starsDelta52w: 21,
      recentIssues12w: 0,
      repositoryScope: 'PACKAGE_SCOPED',
      deprecatedLatest: null,
      deprecationObservedAt: null,
      dependentsDelta: Math.round(last(dependents[2]) - first(dependents[2])),
    },
  ],
}
