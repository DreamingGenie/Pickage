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
 * 지표 카드 하나의 처지.
 *
 * 위 주석이 "실패가 서로 전파되지 않는다" 고 적어 두었지만 **화면은 그렇게 하지 않았다** —
 * 셋 중 하나만 실패해도 탭 전체가 오류로 바뀌었다. 카드가 자기 처지를 들고 있어야
 * 옆 카드와 패키지 카드가 그대로 남는다(`DEC-RECONCILIATION-20260910-01` 8번).
 *
 * `ready` 에 데이터가 딸려 있지 않은 것은 의도한 것이다. 시리즈는 모델이 들고 있고
 * 여기서는 "그릴 수 있는가" 만 말한다. 둘을 한 곳에 담으면 빈 시리즈와 로딩 중을
 * 구분하려고 또 분기하게 된다.
 */
export type MetricState =
  /**
   * 그릴 자료가 있다. `refreshError` 는 **이미 받아 둔 것은 멀쩡한데 갱신만 실패한**
   * 경우다 — 그때 차트를 지우면 읽고 있던 것을 뺏는 셈이라 그대로 두고 한 줄로 알린다.
   * 대신 조용히 넘기지도 않는다. 지금 보는 것이 최신이 아닐 수 있다는 사실은 알려야 한다.
   */
  | { status: 'ready'; refreshError?: unknown; onRetry?: () => void }
  | { status: 'loading' }
  /** 그릴 자료가 아예 없다. 첫 조회부터 실패한 경우다. */
  | { status: 'error'; error: unknown; onRetry: () => void }

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

/** 간격 key → 몇 주마다 한 점. 못 찾으면 매주(1)로 돌아간다. */
export function stepOf(intervalKey: string): number {
  return INTERVALS.find((i) => i.key === intervalKey)?.step ?? 1
}

/**
 * 추이 그래프가 선을 그리기 위한 최소 점 개수.
 * 이보다 적으면 선 대신 "데이터 축적 중"을 띄운다(명세 §4 화면 연결).
 */
export const MIN_POINTS_FOR_LINE = 3

/* ------------------------------------------------------------------ *
 * 표시 버전 (구상안 §5.2)
 * ------------------------------------------------------------------ */

/**
 * 카드 하나가 고른 표시 버전들. **여러 개를 고를 수 있고, 고른 것들을 합한다.**
 *
 * **빈 배열이 "전체"다.** 별도의 `TOTAL` 값을 두지 않는다 — 두면 "전체" 와 "전 major 를
 * 하나씩 다 고름" 이 서로 다른 상태로 갈라지는데, 화면에는 같은 선이 그려진다. 상태가 둘로
 * 갈라지면 어느 쪽이 켜져 있는지 사람도 코드도 헷갈린다.
 *
 * **패키지마다 독립이다.** 전역 선택을 상단에 두지 않는다 — 그러면 major 구성이 서로 다른
 * 패키지들(4·5 만 있는 것과 1~10 이 있는 것)이 한 값을 나눠 가져야 해서, 한쪽에는 없는
 * 버전이 선택되는 상태가 생긴다. 카드 안에 두면 각자 자기 목록에서 고른다.
 *
 * **바꿔도 서버 왕복이 없다.** major 별 시리즈를 한 번에 받아 두었기 때문이다.
 * 기능 비교의 버전과도 다른 축이다 — 이걸 바꾼다고 기능 분석 결과가 무효화되지 않는다.
 */
export type MajorSelection = readonly string[]

/** 아무것도 안 고른 상태 = 전 버전 합계. */
export const ALL_MAJORS: MajorSelection = []

/** major 하나의 선. `points` 는 이미 화면 좌표계(`t`·`v`)다. */
export interface MajorSeries {
  major: string
  points: { t: string; v: number }[]
}

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
  /**
   * 위 증감을 낸 양 끝 스냅샷 날짜(311c). `sampleEvery`가 뒤에서부터 솎으므로 "표시된 첫
   * point"가 구간 시작과 정확히 같지 않을 수 있어, 그 사실을 카드에서 그대로 보여준다.
   */
  dependentsDeltaFrom: string | null
  dependentsDeltaTo: string | null

  /**
   * Version Share 응답 자체의 기준일. 개요의 `snapshotAt`(전체 카드 공통 기준일)과는
   * 다른 값일 수 있어 이름을 구분한다 — 둘을 섞으면 "이 분포가 언제 것인지"를 잘못 말한다.
   */
  versionShareSnapshotAt: string | null

  /**
   * 구상안 §5.2 `availableDisplayVersions` — 이 패키지에서 고를 수 있는 major.
   *
   * **자료가 있는 것만 들어온다.** 서버가 한 번도 0 이 아닌 적이 없던 major 를 아예 보내지
   * 않으므로, 목록에 있으면 그릴 점이 있다는 뜻이다. 빈 배열은 자료가 없는 것이며
   * (스냅샷 미수신) 그때 선택기를 띄우지 않는다.
   *
   * 순서는 서버가 숫자로 세워 보낸 것이다. 화면에서 다시 정렬하지 않는다.
   */
  availableMajors: string[]
}

export interface EcosystemModel {
  /**
   * 0.5 — 모든 현재값의 기준 스냅샷. 항목마다 같으므로 여기 한 번만 둔다.
   * 적재 전이면 `null` 이며, 그때 화면은 기준일 대신 "데이터 축적 중" 을 알린다.
   */
  snapshotAt: string | null
  /** 비교 순서. 요청한 이름 순서 그대로다. 0번이 기준 패키지다. */
  packages: PackageCardModel[]
  /**
   * 화면이 바로 그리는 선. `dependents` 는 **표시 버전이 `TOTAL` 일 때**의 모습이다.
   * 카드에서 버전을 고르면 아래 `dependentsByMajor` 로 다시 만든다.
   */
  series: Record<MetricKey, ChartSeries[]>
  /**
   * 패키지명 → major 별 선. §5 응답을 쪼개진 채로 들고 있는 자리다.
   *
   * 표시 버전을 바꿀 때마다 서버에 묻지 않기 위해 한 번에 받아 둔다. 조회 기간을
   * 상한만큼 한 번에 받는 것과 같은 이유다.
   */
  dependentsByMajor: Record<string, MajorSeries[]>
  /**
   * 0.2 — 요청했지만 없는 이름. 일부가 없어도 200 이므로 화면이 직접 알려야 한다.
   * 지표만 null 인 경우(스냅샷 미수신)와 **다르다**.
   */
  notFound: string[]
  /** 지표별 관측 시작. 시리즈마다 길이가 달라 생기는 것으로, 없으면 전 구간 관측. */
  observedFrom: Partial<Record<MetricKey, string>>
}
