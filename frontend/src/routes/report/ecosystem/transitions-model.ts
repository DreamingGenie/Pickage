/**
 * 유지·유입·이탈 view-model (S15P21A506-361·391).
 *
 * `ecosystem/model.ts`(무거운 변환)가 아니라 `community/model.ts`(wire-근접, 얇은 변환)
 * 쪽 패턴을 따른다 — `TransitionsResponse.series`가 이미 표시에 가까운 모양이라
 * camelCase 변환 + name별 그룹핑 정도만 필요하고, 좌표 재계산 같은 단계가 없다.
 *
 * 로딩·에러·준비 상태는 `model.ts`의 `MetricState`를 그대로 쓴다 — 새로 만들지 않는다.
 */

export type TransitionPeriod = '1y' | '3y' | '5y'

export const TRANSITION_PERIODS: { key: TransitionPeriod; label: string }[] = [
  { key: '1y', label: '1년' },
  { key: '3y', label: '3년' },
  { key: '5y', label: '5년' },
]

/** 요청을 생략했을 때 서버 기본값과 같다(`TransitionPeriod.DEFAULT`, 관측 가능 비중이
 *  49.2%로 세 값 중 가장 균형이 좋다는 백엔드 판단을 그대로 따른다). */
export const DEFAULT_TRANSITION_PERIOD: TransitionPeriod = '3y'

export type TransitionKind = 'regular' | 'peer' | 'optional'

/**
 * package.json 필드 이름(dependencies·peerDependencies·optionalDependencies)을 그대로
 * 쓰면 무엇을 고르는지 짐작하기 어렵다 — 쉬운 한글 두 글자로 줄이고, 정확한 뜻은
 * `KindInfoDialog`(정보 버튼 모달)로 옮긴다. Version Share 안내와 같은 패턴이다.
 */
export const TRANSITION_KINDS: { key: TransitionKind; label: string }[] = [
  { key: 'regular', label: '일반' },
  { key: 'peer', label: '동반' },
  { key: 'optional', label: '선택' },
]

export const TRANSITION_KIND_INFO: { key: TransitionKind; label: string; description: string }[] = [
  {
    key: 'regular',
    label: '일반 (dependencies)',
    description: '이 패키지가 없으면 바로 동작하지 않는, 가장 흔한 의존성입니다.',
  },
  {
    key: 'peer',
    label: '동반 (peerDependencies)',
    description:
      '이 패키지를 쓰는 프로젝트가 직접 같이 설치해서 버전을 맞춰야 하는 의존성입니다. 주로 플러그인·어댑터가 이런 식으로 선언합니다.',
  },
  {
    key: 'optional',
    label: '선택 (optionalDependencies)',
    description: '없어도 동작하지만, 있으면 추가 기능이 켜지는 선택적 의존성입니다.',
  },
]

export type TransitionDataStatus = 'COMPLETE' | 'NO_DATA' | 'OUT_OF_SCOPE' | 'NOT_COMPUTED'

export interface TransitionCounts {
  retained: number
  outflow: number
  unobserved: number
  /** 메인 유입 막대. 원시 유입이 아니라 서버가 이미 뺀 값이다 — 여기서 재계산하지 않는다. */
  inflowAdopted: number
  /** 보조 캡션 전용. 그대로 막대로 그리면 "모든 패키지가 잘나가는" 착시가 생긴다. */
  inflowRaw: number
  inflowNew: number
}

export interface TransitionRow {
  kind: TransitionKind
  dataStatus: TransitionDataStatus
  /** COMPLETE·NO_DATA 일 때만 값이 있다. 나머지는 서버처럼 null — 0으로 바꾸지 않는다. */
  counts: TransitionCounts | null
}

/** 항상 3행(regular·peer·optional), 서버가 보낸 순서 그대로. */
export interface PackageTransitions {
  key: string
  rows: TransitionRow[]
}

export interface TransitionsModel {
  period: TransitionPeriod
  /** 응답 전체가 NOT_COMPUTED 뿐이면 서버가 키 자체를 생략한다 — 그때 둘 다 null. */
  t1: string | null
  t2: string | null
  packages: PackageTransitions[]
  /** ecosystem-view.tsx의 `model.notFound`와 합치지 않는다 — 독립 쿼리라 타이밍이 다르다. */
  notFound: string[]
}

export const EMPTY_TRANSITIONS_MODEL: TransitionsModel = {
  period: DEFAULT_TRANSITION_PERIOD,
  t1: null,
  t2: null,
  packages: [],
  notFound: [],
}
