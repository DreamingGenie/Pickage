import { describe, expect, it } from 'vitest'

import {
  activityShares,
  unobservedShare,
  type TransitionCounts,
  type TransitionRow,
} from '@/routes/report/ecosystem/transitions-model'

/**
 * `react` 1년 구간의 실제 응답값 (S15P21A506-410 의 2026-09-20 코멘트, 운영 DB 전수).
 * 지어낸 수가 아니라 화면에 실제로 실리는 모양이라 분모를 잘못 잡았을 때 눈에 띈다.
 */
const REACT_1Y: TransitionCounts = {
  retained: 4487,
  outflow: 1251,
  unobserved: 171290,
  inflowAdopted: 362,
  inflowRaw: 17039,
  inflowNew: 16677,
}

describe('activityShares', () => {
  /**
   * 이 시험이 깨지면 분모가 `inflowRaw` 로 돌아갔다는 뜻이다. 그러면 유입이 74.8%로 나오는데
   * 그 중 97.9%가 신규 패키지라, 막대에서 신규를 주인공 자리에서 뺀 이유가 분모 쪽으로
   * 그대로 되돌아온다 (S15P21A506-410 의 첫 번째 권고).
   */
  it('분모는 원시 유입이 아니라 채택 유입이다', () => {
    const s = activityShares(REACT_1Y)
    expect(s?.active).toBe(6100)
    expect(s?.retainedPct).toBeCloseTo(73.6, 1)
    expect(s?.inflowAdoptedPct).toBeCloseTo(5.9, 1)
    expect(s?.outflowPct).toBeCloseTo(20.5, 1)
  })

  it('전체는 판정한 수에 릴리스 없음을 더한 것이다', () => {
    expect(activityShares(REACT_1Y)?.total).toBe(177390)
  })

  /** 1만~10만 순위대는 구간에 따라 21%가 여기 해당한다. 0 으로 나누면 화면에 NaN% 가 뜬다. */
  it('판정한 의존자가 하나도 없으면 null 이다', () => {
    const none: TransitionCounts = {
      retained: 0,
      outflow: 0,
      unobserved: 42,
      inflowAdopted: 0,
      inflowRaw: 0,
      inflowNew: 0,
    }
    expect(activityShares(none)).toBeNull()
  })
})

describe('unobservedShare', () => {
  const row = (counts: TransitionCounts | null): TransitionRow => ({
    kind: 'regular',
    dataStatus: counts ? 'COMPLETE' : 'NOT_COMPUTED',
    counts,
  })

  it('여러 행을 합쳐서 낸다', () => {
    expect(unobservedShare([row(REACT_1Y)])).toBeCloseTo(96.6, 1)
  })

  /** 값이 없는 행을 0 으로 세면 비율이 조용히 낮아진다 — 있지도 않은 판정을 만든 셈이 된다. */
  it('값이 없는 행은 분모에서 뺀다', () => {
    expect(unobservedShare([row(REACT_1Y), row(null)])).toBeCloseTo(96.6, 1)
  })

  it('쓸 수 있는 행이 없으면 null 이다 — 경고를 띄우지 않는다', () => {
    expect(unobservedShare([row(null)])).toBeNull()
    expect(unobservedShare([])).toBeNull()
  })
})
