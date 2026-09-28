import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'

import { SAMPLE_ECOSYSTEM } from '@/components/charts/sample'
import { EcosystemView } from '@/routes/report/ecosystem/ecosystem-view'
import {
  DEPENDENTS_CAPTION,
  DEPENDENTS_DELTA_TERM,
  DEPENDENTS_TERM,
} from '@/routes/report/ecosystem/terms'
import { resolvePreset } from '@/routes/report/ecosystem/model'

/**
 * 보고서 1페이지(S15P21A506-405): 기간 프리셋, 용어, 설명 문구의 모달 이전.
 *
 * 좌우 열의 높이 동기화는 jsdom 이 레이아웃을 계산하지 못해 여기서 보지 않는다 — 화면으로 확인한다.
 */

beforeAll(() => {
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

// vitest 전역을 켜지 않아 RTL 이 자동 정리하지 않는다.
afterEach(cleanup)

const presetGroup = () => screen.getByRole('group', { name: '조회 기간 프리셋' })
const pressedPresets = () =>
  within(presetGroup())
    .getAllByRole('button')
    .filter((b) => b.getAttribute('aria-pressed') === 'true')
    .map((b) => b.textContent)
const startSelect = () => screen.getByLabelText('시작일') as HTMLSelectElement
const endSelect = () => screen.getByLabelText('종료일') as HTMLSelectElement

describe('조회 기간 프리셋', () => {
  it('전체 기간 · 반년 · 1년 · 2년 · 3년이 순서대로 있고 처음에는 전체 기간이 눌려 있다', () => {
    render(<EcosystemView model={SAMPLE_ECOSYSTEM} />)
    const labels = within(presetGroup())
      .getAllByRole('button')
      .map((b) => b.textContent)
    expect(labels).toEqual(['전체 기간', '반년', '1년', '2년', '3년'])
    expect(pressedPresets()).toEqual(['전체 기간'])
  })

  it('프리셋을 누르면 세부 기간이 실제 집계 날짜로 바뀐다', async () => {
    const user = userEvent.setup()
    render(<EcosystemView model={SAMPLE_ECOSYSTEM} />)
    const options = [...startSelect().options].map((o) => o.value)

    await user.click(within(presetGroup()).getByRole('button', { name: '반년' }))

    const expected = resolvePreset('6m', options)
    expect(startSelect().value).toBe(expected.start)
    expect(endSelect().value).toBe(expected.end)
    expect(options).toContain(startSelect().value)
    expect(pressedPresets()).toEqual(['반년'])
  })

  it('세부 기간을 직접 고르면 프리셋 선택이 풀린다', async () => {
    const user = userEvent.setup()
    render(<EcosystemView model={SAMPLE_ECOSYSTEM} />)
    const options = [...startSelect().options].map((o) => o.value)

    await user.selectOptions(startSelect(), options[Math.floor(options.length / 2)])

    expect(pressedPresets()).toEqual([])
  })

  it('전체 기간을 다시 누르면 처음 구간으로 돌아온다', async () => {
    const user = userEvent.setup()
    render(<EcosystemView model={SAMPLE_ECOSYSTEM} />)
    const first = startSelect().value
    const last = endSelect().value

    await user.click(within(presetGroup()).getByRole('button', { name: '1년' }))
    await user.click(within(presetGroup()).getByRole('button', { name: '전체 기간' }))

    expect(startSelect().value).toBe(first)
    expect(endSelect().value).toBe(last)
    expect(pressedPresets()).toEqual(['전체 기간'])
  })
})

describe('용어와 설명 문구', () => {
  it('화면에 Dependents 라는 영어 표기를 쓰지 않고 terms 의 한국어 용어로 쓴다', () => {
    const { container } = render(<EcosystemView model={SAMPLE_ECOSYSTEM} />)
    expect(container.textContent).not.toMatch(/Dependents/)
    expect(container.textContent).toContain(DEPENDENTS_TERM)
    expect(container.textContent).toContain(DEPENDENTS_DELTA_TERM)
    // 무엇을 센 값인지는 모달을 열지 않아도 제목 밑에 한 줄로 보인다.
    expect(container.textContent).toContain(DEPENDENTS_CAPTION)
  })

  it('상시 노출하던 설명 문구는 화면에 없다', () => {
    const { container } = render(<EcosystemView model={SAMPLE_ECOSYSTEM} />)
    const text = container.textContent ?? ''
    expect(text).not.toContain('전 버전을 합한 값입니다')
    expect(text).not.toContain('devDependencies)은 세지 않아요')
    expect(text).not.toContain('그래프의 증감과는 세는 방법이 달라요')
    expect(text).not.toContain('그 뒤만 그렸습니다')
  })

  it('의존 등록 수 ⓘ 를 누르면 개념 설명 모달이 열리고, 직접 세지 않는 것과 한계를 밝힌다', async () => {
    const user = userEvent.setup()
    render(<EcosystemView model={SAMPLE_ECOSYSTEM} />)

    await user.click(screen.getByRole('button', { name: `${DEPENDENTS_TERM} 안내` }))

    const dialog = await screen.findByRole('dialog', { name: `${DEPENDENTS_TERM}란?` })
    expect(dialog).toHaveTextContent('package.json')
    expect(dialog).toHaveTextContent('간접 의존)는 세지 않아요')
    // 실제 프로젝트 수·설치량으로 읽히지 않게 한다(기획서 §2, IA 8B).
    expect(dialog).toHaveTextContent('설치 횟수도 아니에요')
  })

  it('표시 버전 ⓘ 모달에 이전에 화면에 있던 설명이 들어 있다', async () => {
    const user = userEvent.setup()
    render(<EcosystemView model={SAMPLE_ECOSYSTEM} />)

    // 카드가 패키지마다 나란히 서므로 버튼도 여럿이다 — 첫 카드(기준 패키지) 것을 연다.
    await user.click(screen.getAllByRole('button', { name: '표시 버전 안내' })[0])

    const dialog = await screen.findByRole('dialog', { name: '표시 버전' })
    expect(dialog).toHaveTextContent('모든 큰 버전(major)을 합한 값이에요')
  })
})

describe('패키지 카드', () => {
  it('고른 패키지마다 카드를 하나씩 나란히 둔다', () => {
    render(<EcosystemView model={SAMPLE_ECOSYSTEM} />)
    for (const p of SAMPLE_ECOSYSTEM.packages) {
      expect(screen.getAllByText(p.key).length).toBeGreaterThan(0)
    }
    expect(screen.getAllByText('추세')).toHaveLength(SAMPLE_ECOSYSTEM.packages.length)
  })

  it('맨 위에 한눈에 보기 요약 자리가 있다', () => {
    render(<EcosystemView model={SAMPLE_ECOSYSTEM} />)
    expect(screen.getByRole('heading', { name: '한눈에 보기' })).toBeInTheDocument()
  })
})
