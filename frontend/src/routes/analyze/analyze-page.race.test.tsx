import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AnalyzePage } from '@/routes/analyze/analyze-page'

/**
 * S15P21A506-472: "직접 찾기" 응답을 기다리는 사이 체크한 후보가 `?with=` 에서 빠졌다.
 *
 * 고른 목록의 최신값을 쥐는 ref 를 렌더 뒤 effect 에서만 맞췄기 때문이다. 주소를 바꾼 순간부터
 * 그 렌더가 끝날 때까지 ref 는 옛 목록이고, 그 틈에 응답이 도착하면 옛 목록에 이름을 붙여 쓴다.
 *
 * **틈을 일부러 연다.** 라우터는 주소 변경을 transition 으로 흘려보내 렌더가 다음 태스크로 밀린다.
 * 그래서 후보를 누른 **같은 동기 구간에서** 대기 중이던 응답을 풀면, 응답의 이어지는 코드
 * (마이크로태스크)가 그 렌더보다 먼저 돈다. `act` 로 감싸면 React 가 렌더와 effect 를 먼저 비워
 * 틈이 닫히므로 이 구간만 `act` 밖에서 한다.
 *
 * 이 시험이 깨지면: 고른 목록을 읽는 자리가 다시 "렌더가 끝난 뒤의 값"에 기대고 있다.
 */

const endpoints = vi.hoisted(() => ({
  fetchPackagesOverview: vi.fn(),
  fetchSimilarPackages: vi.fn(),
  postCommunityRefresh: vi.fn(),
}))

vi.mock('@/api/endpoints', () => endpoints)

vi.mock('@/api/queries', () => ({
  useSimilarPackages: () => ({
    data: {
      not_found: [],
      data_status: 'READY',
      model_ver: 'test',
      candidates: ['luxon', 'immer'].map((name, i) => ({
        rank: i + 1,
        score: 0.9,
        name,
        latest_version: '1.0.0',
        description: '',
      })),
    },
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
  usePackagesOverview: () => ({
    data: { not_found: [], items: [{ name: 'winston' }] },
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock('@/api/autocomplete', () => ({
  usePackageAutocomplete: () => ({ suggestions: [], fallbackPending: false }),
}))

beforeEach(() => {
  endpoints.fetchSimilarPackages.mockResolvedValue({ data_status: 'READY' })
  endpoints.postCommunityRefresh.mockResolvedValue(undefined)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function open(search: string) {
  const router = createMemoryRouter([{ path: '/analyze', element: <AnalyzePage /> }], {
    initialEntries: [`/analyze${search}`],
  })
  render(<RouterProvider router={router} />)
  return router
}

function picked(router: ReturnType<typeof createMemoryRouter>) {
  return new URLSearchParams(router.state.location.search).get('with')?.split(',') ?? []
}

describe('AnalyzePage — 직접 추가와 후보 선택이 겹칠 때', () => {
  it('응답을 기다리는 사이 체크한 후보가 주소에서 빠지지 않는다', async () => {
    let answer!: (value: unknown) => void
    endpoints.fetchPackagesOverview.mockReturnValue(new Promise((resolve) => (answer = resolve)))

    const router = open('?base=winston')
    const input = await screen.findByLabelText('직접 추가할 패키지명')
    fireEvent.change(input, { target: { value: 'dayjs' } })
    fireEvent.click(screen.getByRole('button', { name: '추가' }))
    await waitFor(() => expect(endpoints.fetchPackagesOverview).toHaveBeenCalledWith(['dayjs']))

    // 여기부터 act 밖. 후보를 누르고, 그 렌더가 돌기 전에 대기 중이던 응답을 푼다.
    screen.getByRole('button', { name: 'luxon 비교에 추가' }).click()
    answer({ not_found: [], items: [{ name: 'dayjs' }] })

    await waitFor(() => expect(picked(router)).toContain('dayjs'))
    expect(picked(router)).toEqual(['luxon', 'dayjs'])
  })

  it('겹치지 않으면 예전과 같이 순서대로 쌓인다', async () => {
    endpoints.fetchPackagesOverview.mockResolvedValue({ not_found: [], items: [{ name: 'dayjs' }] })

    const router = open('?base=winston&with=luxon')
    const input = await screen.findByLabelText('직접 추가할 패키지명')
    fireEvent.change(input, { target: { value: 'dayjs' } })
    fireEvent.click(screen.getByRole('button', { name: '추가' }))

    await waitFor(() => expect(picked(router)).toEqual(['luxon', 'dayjs']))
  })
})
