import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { PdfJob } from '@/api/types'
import { PdfExportDialog } from '@/routes/report/_components/pdf-export-dialog'
import type { AnalysisRun } from '@/routes/report/_components/use-analysis-run'

const { generatePdf } = vi.hoisted(() => ({ generatePdf: vi.fn() }))

// 서버 경계에서 목한다 — 이 시험이 보는 것은 모달이 무엇을 보내고 무엇을 보여주는지다.
vi.mock('@/api/endpoints', () => ({
  USE_MOCK: false,
  generatePdf,
  pdfDownloadUrl: (id: string) => `/api/report/pdf/${id}/file`,
}))

/** 기능 비교가 한 번 끝난 상태 — 차단 사유가 없어 준비 화면이 뜬다. */
const RUN = {
  status: 'COMPLETED',
  doneCount: 6,
  elapsedSec: 0,
  hasCompletedOnce: true,
  runId: 1,
  restart: vi.fn(),
} as unknown as AnalysisRun

const JOB: PdfJob = {
  report_id: 'abc123',
  status: 'COMPLETE',
  file_name: 'Pickage_axios-got_2026-09-20.pdf',
  bytes: 72_489,
  created_at: '2026-09-20T04:58:38Z',
  omitted: [],
}

function renderDialog(onPreview = vi.fn(), run: AnalysisRun = RUN) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PdfExportDialog
        open
        onOpenChange={vi.fn()}
        packages={['axios', 'got']}
        transitionPeriod="3y"
        run={run}
        onPreview={onPreview}
        onGoToFeatures={vi.fn()}
      />
    </QueryClientProvider>,
  )
  return { onPreview }
}

beforeEach(() => {
  generatePdf.mockReset()
})

// 전역 자동 정리가 없다 — 남겨 두면 다음 시험에서 같은 문구가 둘로 잡힌다.
afterEach(cleanup)

describe('PdfExportDialog — 준비', () => {
  it('커뮤니티 분석은 이제 실제 내용이 실린다고 안내한다(예전의 "아직 제공되지 않습니다"가 아니다)', () => {
    renderDialog()

    const community = screen.getByRole('checkbox', { name: '커뮤니티 분석' })
    expect(community).toBeEnabled()
    expect(community.closest('label')).toHaveTextContent('핵심 논의')
    expect(community.closest('label')).toHaveTextContent('저장소 수치')
    expect(community.closest('label')).not.toHaveTextContent('아직 제공되지 않습니다')
  })

  it('기능 심화 분석은 여전히 아직 제공되지 않는다고 안내한다', () => {
    renderDialog()

    expect(
      screen.getByRole('checkbox', { name: '기능 심화 분석' }).closest('label'),
    ).toHaveTextContent('아직 제공되지 않습니다')
  })

  it('조건을 주지 않은 조회 기간은 기본값(보유한 전 기간·매주)으로 적고, 그래프와 수치 표가 실린다고 알린다', () => {
    renderDialog()

    expect(screen.getByText('보유한 전 기간 · 매주')).toBeInTheDocument()
    expect(screen.getByText(/그래프와 수치 표/)).toBeInTheDocument()
    expect(screen.getByText(/의존 수\(실제값\)/)).toBeInTheDocument()
  })

  it('골라 둔 구역을 그대로 서버에 보낸다', async () => {
    generatePdf.mockResolvedValue(JOB)
    renderDialog()

    await userEvent.click(screen.getByRole('checkbox', { name: '커뮤니티 분석' }))
    await userEvent.click(screen.getByRole('button', { name: 'PDF 생성' }))

    await waitFor(() => expect(generatePdf).toHaveBeenCalledTimes(1))
    expect(generatePdf.mock.calls[0][0]).toMatchObject({
      names: ['axios', 'got'],
      period: '3y',
      sections: ['COMMUNITY'],
    })
  })
})

describe('PdfExportDialog — 완료', () => {
  async function generate(job: PdfJob, onPreview = vi.fn()) {
    generatePdf.mockResolvedValue(job)
    const view = renderDialog(onPreview)
    await userEvent.click(screen.getByRole('button', { name: 'PDF 생성' }))
    await screen.findByText('PDF가 준비되었습니다')
    return view
  }

  it('닫기·미리보기와 함께 바로 받는 다운로드 버튼이 있다', async () => {
    await generate(JOB)

    // 모달 모서리의 X 도 "닫기" 라서 둘이 잡힌다 — 하단 버튼이 있는지만 본다.
    expect(screen.getAllByRole('button', { name: '닫기' }).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('button', { name: '미리보기' })).toBeInTheDocument()
    // 버튼이 아니라 링크다 — 서버가 attachment 로 보내므로 여는 것만으로 저장된다.
    const download = screen.getByRole('link', { name: /다운로드/ })
    expect(download).toHaveAttribute('href', '/api/report/pdf/abc123/file')
    expect(download).toHaveAttribute('download', 'Pickage_axios-got_2026-09-20.pdf')
  })

  it('미리보기를 거치지 않고도 받을 수 있고, 미리보기 버튼은 그대로 동작한다', async () => {
    const onPreview = vi.fn()
    await generate(JOB, onPreview)

    await userEvent.click(screen.getByRole('button', { name: '미리보기' }))

    expect(onPreview).toHaveBeenCalledWith(JOB)
  })

  it('채우지 못한 구역은 이유를 구역마다 다르게 안내한다', async () => {
    await generate({ ...JOB, omitted: ['COMMUNITY', 'FEATURES'] })

    // 커뮤니티는 기능이 있는데 자료가 없는 것, 기능 심화 분석은 기능 자체가 없는 것이다.
    expect(screen.getByText(/커뮤니티 분석: .*수집되지 않아/)).toBeInTheDocument()
    expect(screen.getByText(/기능 심화 분석: .*기능이 아직 없어/)).toBeInTheDocument()
    expect(screen.queryByText(/커뮤니티 분석: .*기능이 아직 없어/)).toBeNull()
  })

  it('채우지 못한 구역이 없으면 안내를 그리지 않는다', async () => {
    await generate(JOB)

    expect(screen.queryByText(/자리와 사유만 실렸습니다/)).toBeNull()
    expect(screen.queryByText(/수집되지 않아/)).toBeNull()
  })
})

describe('PdfExportDialog — 차단', () => {
  it('선택한 버전이 완료 결과와 달라 재분석이 필요하면 기존 결과가 화면에 있어도 막는다', () => {
    renderDialog(vi.fn(), { ...RUN, reanalysisRequired: true } as AnalysisRun)

    expect(screen.getByText('지금은 PDF를 만들 수 없습니다')).toBeInTheDocument()
    expect(screen.getByText(/재분석이 필요합니다/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'PDF 생성' })).toBeNull()
  })

  it('한 번도 완료되지 않았으면 기능 비교 미실행으로 막는다', () => {
    renderDialog(vi.fn(), { ...RUN, hasCompletedOnce: false } as AnalysisRun)

    expect(screen.getByText('기능 비교 분석이 아직 실행되지 않았습니다.')).toBeInTheDocument()
  })
})
