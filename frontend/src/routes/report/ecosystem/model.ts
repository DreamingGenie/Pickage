import type { ChartSeries } from '@/components/charts/geometry'
import type { ShareGroup } from '@/components/charts/version-share'

/**
 * 생태계 변화 화면의 뷰 모델.
 *
 * `api/types` 는 서버가 보내는 모양(snake_case)이고, 이 파일은 화면이 그리는 모양이다.
 * 사이를 잇는 일은 `adapter.ts` 가 한다. 화면 컴포넌트는 이 타입에만 의존한다.
 *
 * **필드는 v1 API 가 실제로 주는 것만 있다.** 서버가 못 주는 값을 뷰 모델에 두면
 * 화면이 영원히 "미확인"만 그리는 자리를 갖게 된다.
 */

/**
 * 차트로 그리는 지표는 둘뿐이고, 서로 다른 카드에 그린다(명세 §1).
 * 엔드포인트가 갈라져 있어 로딩 시점과 실패가 서로 전파되지 않는다.
 */
export type MetricKey = 'dependents' | 'downloads'

/**
 * x축 구간.
 *
 * "최근 1년" 같은 상대 기간을 쓰지 않는다. 자료가 주간 스냅샷이므로
 * 시작·끝을 **실제 스냅샷 날짜**로 고른다. 그래야 화면에 뜬 구간과
 * 서버가 가진 스냅샷이 정확히 같은 것을 가리킨다.
 */
export interface SnapshotWindow {
  /** ISO date. 응답에 들어 있는 스냅샷 날짜여야 한다. */
  start: string
  end: string
}

/**
 * 한 번에 받아 오는 기간(주).
 *
 * **상한만큼 한 번에 받고 그 뒤로는 서버에 다시 묻지 않는다.** 구간을 좁히고 넓히는 일이
 * 전부 화면 안에서 끝난다.
 *
 * <p>처음에는 "26주 / 52주 / 104주" 버튼으로 서버 조회 범위를 바꾸고, 그와 별개로 시작·끝
 * 드롭다운이 받은 것을 자르게 했었다. 명세 §1 이 "기간만 바꾸면 추이만 다시 받으면 된다" 고
 * 한 것을 그대로 옮긴 결과였는데, **화면에서는 그 둘이 똑같이 "구간 고르기" 로 보인다.**
 * 그래서 이런 것들이 생겼다 —
 *   * 26주 상태에서 "전체" 를 눌러도 26주가 끝이다 (이름과 동작이 어긋난다)
 *   * 넓히려면 위쪽 버튼, 좁히려면 아래쪽 드롭다운이라 어디를 만질지 헷갈린다
 *   * 104주 → 26주 로 줄이면 골라 둔 구간이 초기화된다
 *
 * <p>상한이 104주인 것이 이 선택을 싸게 만든다. 패키지 3개 × 104주 = 점 312개이고,
 * 자료가 주 1회만 바뀌므로 구간을 만질 때마다 다시 받을 이유가 없다.
 */
export const FETCH_WEEKS = 104

/**
 * 스냅샷 표시 간격.
 *
 * **서버 왕복이 없는 축**이다. 이미 받은 점을 화면에서 솎아낼 뿐이다.
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

/**
 * 추이 그래프가 선을 그리기 위한 최소 점 개수.
 * 이보다 적으면 선 대신 "데이터 축적 중"을 띄운다(명세 §4 화면 연결).
 */
export const MIN_POINTS_FOR_LINE = 3

export interface PackageCardModel {
  /** 패키지명. 차트 시리즈 key 와 같다. */
  key: string

  repoUrl: string | null
  latestVersion: string
  /** ISO 8601 UTC */
  publishedAt: string
  description: string | null
  licenses: string[]

  /** 최신 안정 버전에 폐기 표시가 있는지. 패키지가 폐기됐다는 뜻이 아니다. */
  isDeprecated: boolean

  /**
   * **직전 7일 합계**다(명세 §3 화면 연결). 라벨을 "주간 다운로드"로 고정한다 —
   * 일별로 오해되면 규모 감각이 7배 틀어진다.
   * null 은 0 이 아니라 "집계 대기 중"이다.
   */
  downloads: number | null

  /** 저장소 별 수. 스냅샷이 없거나 저장소를 관측 못 했으면 null. */
  stars: number | null
  /**
   * **직전 스냅샷 대비** 증감이다. 52주 누적이 아니다.
   * 첫 스냅샷이라 직전 값이 없으면 null 이고, 화면에서 화살표를 숨긴다.
   */
  starsDelta: number | null

  /** 열린 이슈 수. 등록 건수가 아니라 **현재 열려 있는 수**다. */
  openIssues: number | null
  openIssuesDelta: number | null

  /**
   * major 별 의존 지분. 각 패키지 안에서 합이 100% 다.
   * 빈 배열은 "그 시점에 자료가 없음"이며 에러가 아니다(명세 §6).
   */
  versionShare: ShareGroup[]

  /**
   * 화면에 뜬 구간의 Dependents 순증감.
   * 유입·이탈로 나누지 않는다 — 합계값이라 그렇게 나눌 수 없다.
   */
  dependentsDelta: number | null
}

export interface EcosystemModel {
  /**
   * 0.5 — 모든 현재값의 기준 스냅샷. 항목마다 같으므로 여기 한 번만 둔다.
   * 적재 전이면 `null` 이며, 그때 화면은 기준일 대신 "데이터 축적 중" 을 알린다.
   */
  snapshotAt: string | null
  /** 비교 순서. 요청한 이름 순서 그대로다. 0번이 기준 패키지다. */
  packages: PackageCardModel[]
  series: Record<MetricKey, ChartSeries[]>
  /**
   * 0.2 — 요청했지만 없는 이름. 일부가 없어도 200 이므로 화면이 직접 알려야 한다.
   * 지표만 null 인 경우(스냅샷 미수신)와 **다르다**.
   */
  notFound: string[]
  /** 지표별 관측 시작. 시리즈마다 길이가 달라 생기는 것으로, 없으면 전 구간 관측. */
  observedFrom: Partial<Record<MetricKey, string>>
}
