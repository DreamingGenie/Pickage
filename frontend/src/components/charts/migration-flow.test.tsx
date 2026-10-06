import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { MigrationFlowBar } from '@/components/charts/migration-flow'
import { observationHint } from '@/routes/report/ecosystem/migration-model'
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

describe('서버가 새 필드를 아직 안 보낼 때', () => {
  it('없는 값에 토씨를 붙이려다 화면을 죽이지 않는다', () => {
    // a_pct 는 방금 서버에 더한 필드다. 프런트가 먼저 배포되거나 백엔드만 롤백되면
    // 없는 채로 온다. 그때 undefined.toFixed() 가 render 중에 터지면 이 패널만 비는
    // 것이 아니라 **보고서 페이지 전체가 빈 화면**이 된다 — 라우터의 에러 경계가 받기
    // 때문이고, 이 화면에서 실제로 한 번 겪은 고장 방식이다.
    // 비율만 없으면 알고 있는 수로 문장을 세운다 — 가진 것까지 버리지 않는다.
    expect(observationHint('winston', { name: 'pino', dependents: 397, aPct: undefined })).toBe(
      'winston을 지운 프로젝트 397곳이 pino를 넣었어요',
    )

    // 프로젝트 수만 없으면 괄호를 지우고 비율만 낸다.
    expect(observationHint('winston', { name: 'pino', dependents: undefined, aPct: 8.4 })).toBe(
      'winston을 지운 프로젝트 중 8.4%가 pino를 넣었어요',
    )

    // 둘 다 없을 때만 수를 지어내지 않고 그 사실을 말한다.
    expect(
      observationHint('winston', { name: 'pino', dependents: undefined, aPct: undefined }),
    ).toBe('관측된 수를 받지 못했어요')
  })
})

describe('말풍선 문장', () => {
  it('비율이 앞에 오고 실수가 괄호로 간다', () => {
    expect(observationHint('winston', { name: 'pino', dependents: 50, aPct: 8.4 })).toBe(
      'winston을 지운 프로젝트 중 8.4%(50곳)이 pino를 넣었어요',
    )
  })

  /**
   * 괄호가 붙고 안 붙고에 따라 조사가 갈린다 — "곳" 은 받침이 있고 "퍼센트" 는 없다.
   * 한 쪽만 보고 '가' 로 굳히면 다른 쪽이 "…(50곳)가" 가 된다 (S15P21A506-468 리뷰).
   */
  it('괄호가 붙으면 조사가 이로 바뀐다', () => {
    expect(observationHint('winston', { name: 'pino', dependents: 50, aPct: 8.4 })).toContain(
      '(50곳)이 pino',
    )
    expect(
      observationHint('winston', { name: 'pino', dependents: undefined, aPct: 8.4 }),
    ).toContain('8.4%가 pino')
  })

  it('이름의 받침에 따라 조사가 갈린다', () => {
    // moment(트) 는 받침 없음, axios 도 "스" 로 읽혀 받침 없음. dayjs 는 "에스".
    // 어긋나도 뜻이 달라지지 않는 자리라 근사를 쓴다 — josa.ts 주석 참고.
    expect(observationHint('moment', { name: 'dayjs', dependents: 397, aPct: 20.8 })).toContain(
      'moment를 지운',
    )
    expect(observationHint('winston', { name: 'pino', dependents: 50, aPct: 8.4 })).toContain(
      'winston을 지운',
    )
  })
})
