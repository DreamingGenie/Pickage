import {
  DEFAULT_TRANSITION_PERIOD,
  type TransitionPeriod,
} from '@/routes/report/ecosystem/transitions-model'

/**
 * 이탈 사유 view-model (S15P21A506-396·410).
 *
 * `transitions-model.ts` 와 같은 패턴(wire-근접, 얇은 변환)이되 **더 단순하다** —
 * `kind` 분해가 없어 한 패키지가 한 줄이다.
 *
 * 구간 프리셋과 기본값을 **여기서 다시 정의하지 않고** `transitions-model` 에서 그대로
 * 가져온다. 두 패널이 같은 표(`dependent_transition`)에서 `t1`·`t2` 를 받아 기준일이
 * 구조적으로 같으므로(백엔드 `removal_reasons/load.py`), 프리셋이 갈리면 그 보장이 깨진다.
 */
export type RemovalReasonsPeriod = TransitionPeriod

export type RemovalReasonsDataStatus =
  | 'COMPLETE'
  | 'NO_DATA'
  | 'OUT_OF_SCOPE'
  | 'NOT_COMPUTED'

/**
 * **단위가 `transitions` 와 다르다.** 여기 넷은 전부 "전이 건수"이고
 * 유지·유입·이탈의 넷은 "패키지 수"다. 더하거나 나누면 안 된다 —
 * `outflow` 는 "T1 엔 쓰고 T2 엔 안 쓰는 패키지가 몇 개인가",
 * `removals` 는 "그 사이 빼는 행위가 몇 번 있었나" 다.
 */
export interface RemovalCounts {
  /** 이탈 전이의 수. `noReplacement + withReplacement` 와 항상 같다(DB CHECK). */
  removals: number
  /** 빼고 아무것도 안 넣었다 → 필요가 없어졌다. **이 지표의 결론이라 주인공으로 둔다.** */
  noReplacement: number
  /**
   * 뺀 릴리스에서 다른 것을 함께 넣었다. **같은 자리의 대체라는 보장이 없다** —
   * 한 릴리스에 섞인 대청소일 수 있으므로 화면 문구에 "대체했다" 로 단정하지 않는다.
   */
  withReplacement: number
  /** 뺀 적 있는 **의존자 수**(중복 접음). `removals` 와 단위가 달라 나누지 않는다. */
  dependents: number
}

export interface PackageRemovalReasons {
  key: string
  /** 서버가 값으로 실어 보낸다(`"transitions"`). 캡션에 그대로 쓴다 — 문서는 받는 쪽 코드에 안 닿는다. */
  unit: string
  dataStatus: RemovalReasonsDataStatus
  /** COMPLETE·NO_DATA 일 때만 값이 있다. 나머지는 서버처럼 null — 0 으로 바꾸지 않는다. */
  counts: RemovalCounts | null
}

export interface RemovalReasonsModel {
  period: RemovalReasonsPeriod
  /** 읽을 행이 하나도 없으면 서버가 키 자체를 생략한다 — 그때 둘 다 null. */
  t1: string | null
  t2: string | null
  /** 모집단. 현재는 항상 `npm_all`. 행이 하나도 없으면 null. */
  population: string | null
  packages: PackageRemovalReasons[]
  notFound: string[]
}

export const EMPTY_REMOVAL_REASONS_MODEL: RemovalReasonsModel = {
  period: DEFAULT_TRANSITION_PERIOD,
  t1: null,
  t2: null,
  population: null,
  packages: [],
  notFound: [],
}
