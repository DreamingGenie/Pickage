import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { MigrationFlowBar } from '@/components/charts/migration-flow'
import type {
  MigrationDestination,
  PackageMigration,
} from '@/routes/report/ecosystem/migration-model'

afterEach(cleanup)

/**
 * **남는 자리를 말하는 두 줄**만 본다 (S15P21A506-424).
 *
 * 이 막대에서 남는 자리는 장식이 아니라 요점이다 — "관측된 이동 중 얼마나 집계에 못
 * 들어왔나" 를 말하는 유일한 자리다. 그 수가 스스로 모순되면(합이 101%, 또는 "나머지 0%를
 * 뺐어요") 화면이 가장 중요한 한 줄에서 신뢰를 잃는다.
 *
 * 둘 다 `/code-review` 가 찾은 것이라 회귀로 고정한다.
 */

const dest = (name: string, sharePmPct: number): MigrationDestination => ({
  name,
  sharePmPct,
  votes: 20,
  publisherMonths: 14,
  dependents: 397,
  aPct: 20.8,
  evidence: 'recommended',
  variant: false,
  firstSeen: '2019-03-11',
  lastSeen: '2026-07-28',
})

const pkg = (destinations: MigrationDestination[]): PackageMigration => ({
  key: 'winston',
  snapshotAt: '2026-08-31',
  shareBasis: 'publisher_months',
  dataStatus: 'COMPLETE',
  destinations,
  etc: null,
  observedPairs: destinations.length,
})

describe('남는 자리의 비율', () => {
  it('들어온 몫과 빠진 몫의 합이 100 이다', () => {
    // 44.5 와 55.5 를 각자 반올림하면 45 + 56 = 101 이 된다. 눈으로 막대를 볼 수 없는
    // 사용자에게만 보이는 수라 더 오래 살아남는다. RemovalBars 가 같은 규칙을 쓴다.
    const { container } = render(<MigrationFlowBar pkg={pkg([dest('pino', 44.5)])} />)

    const label = container.querySelector('[role="img"]')!.getAttribute('aria-label')!
    const [covered, dropped] = [...label.matchAll(/(\d+)%/g)].map((m) => Number(m[1]))

    expect(covered + dropped).toBe(100)
  })

  it('반올림하면 0 이 되는 나머지는 "1% 미만" 이라고 쓴다', () => {
    // 합이 99.6 이면 나머지가 0.4 다. "나머지 0% 는 뺐어요" 는 자기 모순이라 — 0% 는
    // 뺀 것이 없다는 뜻인데 문장은 뺐다고 말한다.
    render(<MigrationFlowBar pkg={pkg([dest('pino', 99.6)])} />)

    expect(screen.getByText(/1% 미만/)).toBeTruthy()
  })

  it('나머지가 아예 없으면 그 줄을 쓰지 않는다', () => {
    render(<MigrationFlowBar pkg={pkg([dest('pino', 100)])} />)

    expect(screen.queryByText(/근거가 약해 집계에서 뺐어요/)).toBeNull()
  })
})
