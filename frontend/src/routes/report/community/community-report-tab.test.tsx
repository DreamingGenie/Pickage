import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { CommunityStatusResponse } from '@/api/types'
import { CommunityReportTab } from '@/routes/report/community/community-report-tab'
import { SAMPLE_COMMUNITY_RESULT } from '@/routes/report/community/sample'

const { fetchCommunityStatus, postCommunityRefresh } = vi.hoisted(() => ({
  fetchCommunityStatus: vi.fn(),
  postCommunityRefresh: vi.fn(),
}))

// 실제 USE_MOCK 상태머신(api/mock/community.ts) 대신 endpoints 경계에서 직접 목한다 —
// 폴링 타이밍에 기대지 않고 각 시나리오를 결정적으로 구성하기 위해서다.
vi.mock('@/api/endpoints', () => ({
  USE_MOCK: false,
  fetchCommunityStatus,
  postCommunityRefresh,
}))

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const IDLE: CommunityStatusResponse = {
  package_name: 'winston',
  view_status: 'IDLE',
  freshness: null,
  refresh: null,
  result: null,
}

beforeEach(() => {
  fetchCommunityStatus.mockReset()
  postCommunityRefresh.mockReset()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('CommunityReportTab', () => {
  it('기준 패키지 문맥이 없으면 실호출 없이 안내만 표시한다', () => {
    renderWithClient(<CommunityReportTab basePackage={null} baseConflict={false} active />)

    expect(screen.getByText(/기준 패키지 정보가 없어/)).toBeInTheDocument()
    expect(fetchCommunityStatus).not.toHaveBeenCalled()
    expect(postCommunityRefresh).not.toHaveBeenCalled()
  })

  it('basePackage 충돌 시 실호출 없이 충돌 안내만 표시한다', () => {
    renderWithClient(<CommunityReportTab basePackage={null} baseConflict={true} active />)

    expect(screen.getByText(/일치하지 않습니다/)).toBeInTheDocument()
    expect(fetchCommunityStatus).not.toHaveBeenCalled()
  })

  it('IDLE 이면 재진입 시 자동으로 TAB_OPENED POST 를 한 번 보낸다', async () => {
    fetchCommunityStatus.mockResolvedValue(IDLE)
    postCommunityRefresh.mockResolvedValue({
      ...IDLE,
      view_status: 'PROCESSING',
      refresh: {
        refresh_id: 'r1',
        status: 'QUEUED',
        stage: null,
        stage_message: '대기열에서 기다리는 중입니다.',
        started_at: null,
        last_updated_at: '2026-09-15T00:00:00Z',
        poll_after_seconds: 2,
        retry_at: null,
        error_code: null,
      },
    })

    renderWithClient(<CommunityReportTab basePackage="winston" baseConflict={false} active />)

    await waitFor(() => expect(postCommunityRefresh).toHaveBeenCalledTimes(1))
    expect(postCommunityRefresh).toHaveBeenCalledWith('winston', 'TAB_OPENED')
    expect(await screen.findByText('대기열에서 기다리는 중입니다.')).toBeInTheDocument()
  })

  it('RESULT/FRESH 면 자동 POST 없이 결과만 표시한다', async () => {
    fetchCommunityStatus.mockResolvedValue({
      package_name: 'winston',
      view_status: 'RESULT',
      freshness: 'FRESH',
      refresh: null,
      result: SAMPLE_COMMUNITY_RESULT,
    } satisfies CommunityStatusResponse)

    renderWithClient(<CommunityReportTab basePackage="winston" baseConflict={false} active />)

    expect(
      await screen.findByText(SAMPLE_COMMUNITY_RESULT.repository!.full_name),
    ).toBeInTheDocument()
    expect(postCommunityRefresh).not.toHaveBeenCalled()
  })
})
