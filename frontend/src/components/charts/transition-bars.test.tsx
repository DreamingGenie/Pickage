import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { TransitionBars } from '@/components/charts/transition-bars'
import type { TransitionCounts } from '@/routes/report/ecosystem/transitions-model'

afterEach(cleanup)

/**
 * 분해 하위 막대가 **부모(`릴리스 없음`)보다 길어지지 않는지**만 본다 (S15P21A506-431).
 *
 * 값이 0 이 아닌데 막대가 안 보이는 것을 막으려고 최소 폭을 주는데, 그것을 하위 줄에도
 * 주면 순위 차가 큰 비교에서 부모와 하위가 전부 바닥값에 걸려 **하위 둘의 합이 부모의 두 배**로
 * 보인다. 그러면 한 칸의 분해가 아니라 더 큰 별도 범주로 읽힌다 — 눈으로는 "작은 막대 몇 개"로만
 * 보여 지나치기 쉬운 종류라 여기서 고정한다.
 *
 * **`mode="value"` 를 명시해야 한다** (S15P21A506-468). 화면에서 값/비율 토글이 빠지면서
 * 기본값이 `ratio`(도넛)로 바뀌었다 — 생략하면 막대 자체가 그려지지 않아 이 시험이 지키려는
 * 것을 못 본다. 막대 코드는 화면에서 부르는 곳이 없어졌지만, 토글을 되살릴 때를 위해
 * 이 시험이 계속 지킨다.
 */
const tiny: TransitionCounts = {
  retained: 10,
  outflow: 3,
  unobserved: 1500,
  inflowAdopted: 5,
  inflowRaw: 5,
  inflowNew: 0,
  unobservedFreshness: { recent: 0, stale: 500, dormant: 1000 },
}

/** 화면에 그려진 막대들의 폭(%)을 순서대로. 라벨 순서는 유지·유입·이탈·릴리스 없음·분해다. */
function barWidths(container: HTMLElement): number[] {
  return [...container.querySelectorAll<HTMLElement>('span[style*="width"]')].map((el) =>
    Number.parseFloat(el.style.width),
  )
}

describe('TransitionBars — 관측불가 분해 막대', () => {
  it('하위 막대의 합이 부모 막대를 넘지 않는다', () => {
    // 큰 패키지와 함께 비교하는 상황: 이 행의 값은 전부 공유 스케일의 2% 미만이다.
    const { container } = render(
      <TransitionBars counts={tiny} dataStatus="COMPLETE" max={100000} mode="value" />,
    )
    const widths = barWidths(container)

    expect(widths).toHaveLength(6) // 네 범주 + 분해 둘(3~5년 전·5년 초과)
    const [, , , unobserved, stale, dormant] = widths
    expect(stale + dormant).toBeLessThanOrEqual(unobserved)
    // 하위는 바닥값에 걸리지 않고 실제 비율대로 그려진다.
    expect(stale).toBeCloseTo(0.5, 2)
    expect(dormant).toBeCloseTo(1, 2)
  })

  it('분해를 모르면 하위 막대를 그리지 않는다', () => {
    const { container } = render(
      <TransitionBars
        counts={{ ...tiny, unobservedFreshness: null }}
        dataStatus="COMPLETE"
        max={100000}
        mode="value"
      />,
    )
    expect(barWidths(container)).toHaveLength(4)
  })
})
