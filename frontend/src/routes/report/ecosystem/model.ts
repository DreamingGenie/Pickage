import type { ChartSeries } from '@/components/charts/geometry'
import type { ShareGroup } from '@/components/charts/version-share'

/**
 * 03A 생태계 변화 화면의 뷰 모델.
 *
 * `api/types` 는 Spring 스펙이 확정되면 통째로 갈릴 초안이라,
 * 화면이 실제로 요구하는 모양은 여기에 따로 둔다.
 */

/**
 * 차트로 그리는 지표는 둘뿐이고, 서로 다른 카드에 그린다(IA 8.1).
 * 수집 경로·범위·갱신 주기가 달라서 한 축에 겹쳐 놓으면 안 된다.
 */
export type MetricKey = 'dependents' | 'downloads'

/** Dependency 표시 버전. 패키지마다 독립이며 기능 분석 캐시를 무효화하지 않는다(구상안 1.2). */
export const TOTAL = 'TOTAL'

/**
 * x축 구간.
 *
 * "최근 1년" 같은 상대 기간을 쓰지 않는다. 자료가 주간 스냅샷이므로
 * 시작·끝을 **실제 스냅샷 날짜**로 고른다. 그래야 화면에 뜬 구간과
 * 서버가 가진 스냅샷이 정확히 같은 것을 가리킨다.
 */
export interface SnapshotWindow {
  /** ISO date. 목록에 있는 스냅샷 날짜여야 한다. */
  start: string
  end: string
}

/**
 * 스냅샷 표시 간격.
 *
 * deps.dev 스냅샷은 매주 월요일에 만들어진다. 화면에서 몇 주마다 볼지는
 * 사용자가 고른다 — 촘촘하면 잡음이 보이고 성기면 추세가 보인다.
 *
 * 값을 평균 내지 않는다. 고른 주의 관측치를 그대로 쓴다.
 */
export interface IntervalOption {
  key: string
  label: string
  /** 몇 주마다 한 점 */
  step: number
}

export const INTERVALS: IntervalOption[] = [
  { key: '1w', label: '매주', step: 1 },
  { key: '2w', label: '2주', step: 2 },
  { key: '4w', label: '4주', step: 4 },
  { key: '13w', label: '분기', step: 13 },
]

export interface PackageCardModel {
  /** 패키지명. 차트 시리즈 key 와 같다. */
  key: string
  /** 표시 버전 목록. 항상 TOTAL 을 포함한다. */
  availableDisplayVersions: string[]
  selectedDisplayVersion: string

  versionShare: ShareGroup[]

  /** 저장소 별 수. 저장소 연결이 검증되지 않았으면 null. */
  stars: number | null
  /** 최근 52주 별 증감. */
  starsDelta52w: number | null

  /**
   * 최근 12주 새 Issue 등록 수.
   * null 은 "0건"이 아니라 저장소 미검증·수집 실패다.
   */
  recentIssues12w: number | null
  repositoryScope: 'PACKAGE_SCOPED' | 'REPOSITORY_WIDE' | 'AMBIGUOUS' | 'UNVERIFIED'

  /**
   * 최신 안정 버전에 폐기 표시가 있는지.
   * null = 미확인. 폐기 "시점"은 과거 스냅샷을 안 받아 알 수 없다.
   */
  deprecatedLatest: boolean | null
  deprecationObservedAt: string | null

  /**
   * 기간 대비 Dependents 순증감.
   * 유입·이탈로 나누지 않는다 — 현재 수집 범위로는 증감만 관측된다.
   */
  dependentsDelta: number | null
}

export interface EcosystemModel {
  /** 비교 순서. 0번이 기준 패키지이며 해제할 수 없다(IA 6.3). */
  packages: PackageCardModel[]
  series: Record<MetricKey, ChartSeries[]>
  period: { from: string; to: string }
  /** 지표별 관측 시작. 없으면 전 구간 관측. */
  observedFrom: Partial<Record<MetricKey, string>>
  /** 지표별 수집 한계 설명. 범위 선택지가 잠겼을 때 이유로 쓴다. */
  coverageNote?: Partial<Record<MetricKey, string>>
}
