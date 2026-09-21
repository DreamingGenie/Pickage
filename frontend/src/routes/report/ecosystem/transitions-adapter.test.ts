import { describe, expect, it } from 'vitest'

import type { TransitionSeriesItem, TransitionsResponse } from '@/api/types'
import { toTransitionsModel } from '@/routes/report/ecosystem/transitions-adapter'

/**
 * 관측불가 분해의 계약 규칙만 본다 (S15P21A506-421·431).
 *
 * 이 셋은 다른 필드와 달리 **`data_status` 와 독립적으로 없을 수 있다.** 어댑터가 그것을
 * 0 으로 메우면 화면에 "5년 넘게 방치된 의존자가 0명" 이라는, 숫자가 맞아 보이는 거짓이
 * 실린다 — 눈으로는 잡히지 않는 종류라 시험으로 고정한다.
 */
const base: TransitionSeriesItem = {
  name: 'react',
  kind: 'regular',
  population: 'npm_all',
  retained: 4673,
  inflow: 112435,
  inflow_new: 111785,
  inflow_adopted: 650,
  outflow: 1310,
  unobserved: 75628,
  unobserved_recent: 0,
  unobserved_stale: 28890,
  unobserved_dormant: 46738,
  data_status: 'COMPLETE',
}

const responseOf = (item: TransitionSeriesItem): TransitionsResponse => ({
  metric: 'dependent_transitions',
  period: '3y',
  t1: '2023-08-31',
  t2: '2026-08-31',
  series: [item],
  not_found: [],
})

const freshnessOf = (item: TransitionSeriesItem) =>
  toTransitionsModel(responseOf(item), ['react']).packages[0]?.rows[0]?.counts?.unobservedFreshness

describe('toTransitionsModel — 관측불가 분해', () => {
  it('세 값이 오면 그대로 싣는다', () => {
    expect(freshnessOf(base)).toEqual({ recent: 0, stale: 28890, dormant: 46738 })
  })

  /** 마이그레이션 배포와 88만 행 재적재 사이의 행 — 2026-09-21 운영에서 약 30분 있었다. */
  it('COMPLETE 라도 셋이 없으면 null 이다 — 나머지 값은 그대로 쓴다', () => {
    const row = toTransitionsModel(
      responseOf({
        ...base,
        unobserved_recent: null,
        unobserved_stale: null,
        unobserved_dormant: null,
      }),
      ['react'],
    ).packages[0]?.rows[0]
    expect(row?.counts?.unobserved).toBe(75628)
    expect(row?.counts?.unobservedFreshness).toBeNull()
  })

  it('셋 중 하나만 없어도 분해를 쓰지 않는다', () => {
    expect(freshnessOf({ ...base, unobserved_stale: null })).toBeNull()
  })

  /**
   * 서버에 합계 DB CHECK 가 있으므로 정상 경로에서는 일어나지 않는다. 일어났다면 CSV/COPY
   * 경계에서 열 짝이 밀린 것이고, 그 상태로 그린 그림은 곧 거짓이다.
   */
  it('합이 관측불가와 어긋나면 버린다', () => {
    expect(freshnessOf({ ...base, unobserved_dormant: 46739 })).toBeNull()
  })
})
