import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'

import { ServiceIntroPage } from '@/routes/intro/service-intro-page'

/**
 * 서비스 소개 첫 화면(S15P21A506-404).
 *
 * 레이아웃(전폭 히어로·카드 높이)은 jsdom 이 계산하지 못하므로 여기서 보지 않는다 — 그쪽은 화면으로
 * 확인한다. 이 시험이 지키는 것은 **문구 계약**이다. 인트로는 코드가 아니라 말이 서비스를 약속하는
 * 화면이라, 금지 용어가 슬쩍 들어오는 회귀가 가장 값싸게 일어난다.
 */

beforeAll(() => {
  // useStepCycle(모션 설정)과 LineChart(폭 측정)가 브라우저 API 를 쓴다. jsdom 에는 없다.
  window.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
    onchange: null,
  })) as typeof window.matchMedia
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as typeof ResizeObserver
})

// vitest 전역을 켜지 않아 RTL 이 자동 정리하지 않는다. 앞 시험의 렌더가 남으면 getByText 가 중복을 찾는다.
afterEach(cleanup)

function renderIntro() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ServiceIntroPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ServiceIntroPage 문구', () => {
  it('히어로 제목은 한 줄 한 문구다', () => {
    renderIntro()
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1).toHaveTextContent('패키지 선택에, 확인할 근거를')
    expect(h1.querySelector('br')).toBeNull()
  })

  it('히어로 설명은 유사 후보·근거·PDF 공유를 말한다', () => {
    const { container } = renderIntro()
    const text = container.textContent ?? ''
    expect(text).toContain(
      '유사한 기능을 가진 패키지를 제안하고, 믿을 수 있는 근거와 함께 분석을 제공합니다.',
    )
    expect(text).toContain('PDF로 다운로드 받아 팀원들과 공유하세요.')
  })

  it('1단계는 입력을 청하고 데이터가 있어야 확인된다는 경고를 예시 이미지 아래에 둔다', () => {
    const { container } = renderIntro()
    const text = container.textContent ?? ''
    expect(text).toContain('고민하고 계신 패키지를 입력해 주세요')
    expect(text).toContain('수집된 데이터가 있어야, 결과를 확인할 수 있습니다.')
  })

  it('2단계는 후보 두 개까지 고른다고 말하고, 후보에 없을 때 검색하라고 안내한다', () => {
    const { container } = renderIntro()
    const text = container.textContent ?? ''
    expect(text).toContain('비교하실 패키지를 선택하세요. 총 2개 선택하실 수 있습니다.')
    expect(text).toContain('찾는 패키지가 후보에 없다면, 검색해서 추가하세요.')
    // 기준 패키지는 해제할 수 없고, 후보는 전부 미선택으로 시작한다(IA 6.3).
    expect(screen.getByText('해제 불가')).toBeInTheDocument()
    expect(screen.getByText('1 / 3 선택됨')).toBeInTheDocument()
  })

  it('줄은 마침표·쉼표 뒤에서만 바뀐다 — 마지막이 아닌 절은 . 또는 , 로 끝난다', () => {
    const { container } = renderIntro()
    const clauses = [...container.querySelectorAll('[data-clause]')]
    expect(clauses.length).toBeGreaterThan(0)
    for (const el of clauses) {
      const next = el.nextElementSibling
      if (next?.hasAttribute('data-clause')) {
        // 다음 절이 있다 = 여기가 줄바꿈 후보 자리다. 뜻이 끊기지 않는 자리(문장 부호 뒤)여야 한다.
        expect(el.textContent, `"${el.textContent}" 뒤에서 줄이 바뀔 수 있다`).toMatch(/[.,]$/)
      }
    }
  })

  it('예시로 둘러보기 패키지는 express · yaml · axios 다', () => {
    renderIntro()
    const group = screen.getByText('예시로 둘러보기').parentElement as HTMLElement
    const names = [...group.querySelectorAll('button')].map((b) => b.textContent)
    expect(names).toEqual(['express', 'yaml', 'axios'])
  })

  it('IA 금지 용어를 쓰지 않는다', () => {
    const { container } = renderIntro()
    const text = container.textContent ?? ''
    for (const banned of ['확인 불가', '대시보드', '최고의 대안', '추천 1위', '승자']) {
      expect(text, `금지 용어 "${banned}"`).not.toContain(banned)
    }
  })

  it('3단계의 의존 수 증감은 아래 분석 결과 예시와 같은 값이다', () => {
    renderIntro()
    const values = screen
      .getAllByText('의존 수 증감')
      .map((label) => label.nextElementSibling?.textContent?.trim())
    // 3단계 예시 + 예시 보고서의 기준 패키지 카드. 손으로 적은 숫자가 아니라 같은 계산이어야 한다.
    expect(values.length).toBeGreaterThanOrEqual(2)
    expect(new Set(values).size).toBe(1)
  })
})
