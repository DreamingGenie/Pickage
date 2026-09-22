import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
    expect(h1).toHaveTextContent('비교하고 고르는 npm 패키지')
    expect(h1.querySelector('br')).toBeNull()
  })

  it('히어로 설명은 무엇을 넣고 무엇을 받는지 말하고, 첫 화면에 예시 버튼·안내 링크를 두지 않는다', () => {
    const { container } = renderIntro()
    expect(container.textContent).toContain(
      '비슷한 패키지를 찾아 쓰임새·기능·커뮤니티를 한눈에 비교하고,',
    )
    expect(screen.queryByText('예시로 둘러보기')).toBeNull()
    expect(screen.queryByText('처음이라면 이 조합부터 눌러 보세요')).toBeNull()
  })

  it('따라하기는 여섯 장이고, 번호를 누르면 그 장으로 바로 간다', async () => {
    const user = userEvent.setup()
    renderIntro()
    const tabs = within(screen.getByRole('tablist', { name: '사용 설명서 목차' })).getAllByRole(
      'tab',
    )
    expect(tabs).toHaveLength(6)
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')

    await user.click(tabs[3])
    expect(tabs[3]).toHaveAttribute('aria-selected', 'true')
    expect(tabs[0]).toHaveAttribute('aria-selected', 'false')
  })

  it('따로 낱말 풀이를 두지 않고, 장마다 무엇을 할 수 있는지 한 문장으로 말한다', () => {
    const { container } = renderIntro()
    expect(container.textContent).not.toContain('화면에 나오는 말 풀이')
    expect(container.textContent).toContain(
      '알아보고 싶은 패키지를 검색하여 유사한 패키지를 확인해요.',
    )
    expect(container.textContent).toContain(
      '패키지에 관해 어떤 이야기가 오고 가는지 엿볼 수 있어요.',
    )
  })

  it('의존 수를 실제 사용량처럼 부르지 않는다', () => {
    const { container } = renderIntro()
    for (const banned of ['사용처', '프로젝트가 사용', '가져다 쓰는 수']) {
      expect(container.textContent).not.toContain(banned)
    }
  })

  it('핵심 기능 셋은 한 줄씩 차지하고, 버튼은 다른 화면으로 보내지 않고 미리보기 창을 연다', async () => {
    const user = userEvent.setup()
    renderIntro()
    const section = screen.getByRole('region', { name: 'Pickage 핵심 기능' })
    const titles = [...section.querySelectorAll('h3')].map((h) => h.textContent)
    expect(titles).toEqual([
      '얼마나 쓰이고 있을까?동향을 비교해요.',
      '무엇이 다를까?기능을 비교해요.',
      '팀과 함께 봐야 한다면?보고서로 확인해요.',
    ])
    expect(within(section).queryAllByRole('link')).toHaveLength(0)

    await user.click(within(section).getByRole('button', { name: '기능 비교 미리보기' }))
    const dialog = await screen.findByRole('dialog', { name: '기능 비교 미리보기' })
    // 설치 정보 표는 보고서의 실제 컴포넌트다
    expect(
      within(dialog).getByRole('region', { name: '설치하기 전에 알아 둘 것' }),
    ).toBeInTheDocument()
  })

  it('없어진 근거 보기(Evidence Drawer)를 약속하지 않는다', () => {
    const { container } = renderIntro()
    expect(container.textContent).not.toContain('근거 발췌')
  })

  it('IA 금지 용어를 쓰지 않는다', () => {
    const { container } = renderIntro()
    const text = container.textContent ?? ''
    for (const banned of ['확인 불가', '대시보드', '최고의 대안', '추천 1위', '승자']) {
      expect(text, `금지 용어 "${banned}"`).not.toContain(banned)
    }
  })

  it('관측 범위와 판단 한계를 자주 묻는 질문으로 남긴다 — 후보 순서는 우열이 아니다', () => {
    const { container } = renderIntro()
    expect(screen.getByRole('heading', { name: '자주 묻는 질문' })).toBeInTheDocument()
    expect(container.textContent).toContain('품질이나 우열이 아니에요')
  })
})
