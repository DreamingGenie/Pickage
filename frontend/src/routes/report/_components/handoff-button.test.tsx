import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { MarkdownJob } from '@/api/types'
import { HandoffButton } from '@/routes/report/_components/handoff-button'
import type { AnalysisRun } from '@/routes/report/_components/use-analysis-run'

const { generateHandoff } = vi.hoisted(() => ({ generateHandoff: vi.fn() }))

// 서버 경계에서 목한다 — pdf-export-dialog.test.tsx 와 같은 방식이다.
vi.mock('@/api/endpoints', () => ({
  USE_MOCK: false,
  generateHandoff,
  markdownDownloadUrl: (id: string) => `/api/report/markdown/${id}/file`,
}))

/** 기능 비교가 한 번 끝난 상태 — 자격 조건을 통과한다(pdf-export-dialog.test.tsx 의 RUN 과 같다). */
const RUN = {
  status: 'COMPLETED',
  doneCount: 6,
  elapsedSec: 0,
  hasCompletedOnce: true,
  runId: 1,
  restart: vi.fn(),
  rawResult: null,
} as unknown as AnalysisRun

const JOB: MarkdownJob = {
  report_id: 'md-abc123',
  file_name: 'Pickage_axios-got_2026-09-20.md',
  bytes: 9_842,
  created_at: '2026-09-20T04:58:38Z',
  omitted: [],
}

function renderButton(run: AnalysisRun = RUN) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <HandoffButton packages={['axios', 'got']} transitionPeriod="3y" run={run} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  generateHandoff.mockReset()
})

// 전역 자동 정리가 없다 — 남겨 두면 다음 시험에서 같은 문구가 둘로 잡힌다.
afterEach(cleanup)

describe('HandoffButton', () => {
  it('접근성 이름에 "다운로드" 단어를 쓰지 않는다 (pdf-export-dialog.test.tsx 의 /다운로드/ 쿼리와 안 겹치게)', () => {
    renderButton()

    expect(screen.getByRole('button', { name: /HAND-OFF/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /다운로드/ })).not.toBeInTheDocument()
  })

  it('준비됐으면 눌렀을 때 항상 커뮤니티·기능 심화 분석을 함께 요청한다 (구역 선택 없음)', async () => {
    const user = userEvent.setup()
    generateHandoff.mockResolvedValue(JOB)
    renderButton()

    await user.click(screen.getByRole('button', { name: /HAND-OFF/ }))

    await waitFor(() => expect(generateHandoff).toHaveBeenCalledTimes(1))
    expect(generateHandoff.mock.calls[0][0]).toMatchObject({
      names: ['axios', 'got'],
      period: '3y',
    })
    // 구역 선택 UI가 없다 — sections 필드 자체가 요청에 없다(항상 전체를 서버가 시도).
    expect(generateHandoff.mock.calls[0][0]).not.toHaveProperty('sections')
    expect(generateHandoff.mock.calls[0][0].features).toBeUndefined()
  })

  it('기능 비교 완료 결과가 있으면 payload 로 실어 보낸다', async () => {
    const user = userEvent.setup()
    generateHandoff.mockResolvedValue(JOB)
    const rawResult = {
      dataStatus: 'COMPLETE',
      packages: [{ package: 'axios', version: '1.7.7' }],
      features: [],
      narrative: [],
      narrativeError: null,
      sources: [],
    }
    renderButton({ ...RUN, rawResult } as unknown as AnalysisRun)

    await user.click(screen.getByRole('button', { name: /HAND-OFF/ }))

    await waitFor(() => {
      const payload = generateHandoff.mock.calls[0]?.[0]
      expect(payload?.features).toBeDefined()
      expect(payload?.features?.packages).toEqual([{ package_name: 'axios', version: '1.7.7' }])
    })
  })

  it('성공하면 숨은 링크로 다운로드를 자동으로 튼다', async () => {
    const user = userEvent.setup()
    generateHandoff.mockResolvedValue(JOB)
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    renderButton()

    await user.click(screen.getByRole('button', { name: /HAND-OFF/ }))

    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1))
    clickSpy.mockRestore()
  })

  it('기능 비교를 한 번도 완료하지 않았으면 요청을 보내지 않는다', async () => {
    const user = userEvent.setup()
    renderButton({ ...RUN, hasCompletedOnce: false } as AnalysisRun)

    await user.click(screen.getByRole('button', { name: /HAND-OFF/ }))

    expect(generateHandoff).not.toHaveBeenCalled()
  })

  it('재분석이 필요하면(선택 버전과 완료 결과가 다름) 요청을 보내지 않는다', async () => {
    const user = userEvent.setup()
    renderButton({ ...RUN, reanalysisRequired: true } as AnalysisRun)

    await user.click(screen.getByRole('button', { name: /HAND-OFF/ }))

    expect(generateHandoff).not.toHaveBeenCalled()
  })

  it('실패하면 버튼 옆에 오류 문구를 보여준다', async () => {
    const user = userEvent.setup()
    generateHandoff.mockRejectedValue(new Error('network'))
    renderButton()

    await user.click(screen.getByRole('button', { name: /HAND-OFF/ }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
