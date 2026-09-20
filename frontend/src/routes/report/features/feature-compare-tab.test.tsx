import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import {
  FEATURE_NOT_AVAILABLE,
  type FeatureCellWire,
  type FeatureComparisonResponse,
  type FeatureTarget,
  type FeatureVersionsResponse,
} from '@/api/types'
import { useAnalysisRun } from '@/routes/report/_components/use-analysis-run'
import { FeatureCompareTab } from '@/routes/report/features/feature-compare-tab'

const { fetchFeatureVersions, fetchFeatureComparison } = vi.hoisted(() => ({
  fetchFeatureVersions: vi.fn(),
  fetchFeatureComparison: vi.fn(),
}))

// 실제 mock 데이터·지연 대신 endpoints 경계에서 직접 목한다 — 시나리오를 결정적으로 구성한다.
// USE_MOCK 이 false 라 진행 단계 흉내도 돌지 않는다(응답이 오면 곧바로 완료).
vi.mock('@/api/endpoints', () => ({
  USE_MOCK: false,
  fetchFeatureVersions,
  fetchFeatureComparison,
}))

const NAMES = ['pino', 'winston']
const onOpenEvidence = vi.fn()

function Harness({ names = NAMES }: { names?: string[] }) {
  const run = useAnalysisRun(names)
  return <FeatureCompareTab packages={names} run={run} onOpenEvidence={onOpenEvidence} />
}

function renderTab(names = NAMES) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Harness names={names} />
    </QueryClientProvider>,
  )
}

const VERSIONS: Record<string, string[]> = {
  pino: ['10.3.1', '10.2.0'],
  winston: ['3.19.0', '3.18.3'],
}

function versionsFor(names: string[]): FeatureVersionsResponse {
  return {
    packages: names.map((name) => ({
      package_name: name,
      latest_stable: VERSIONS[name][0],
      versions: VERSIONS[name].map((version) => ({ version, prerelease: false })),
    })),
  }
}

function cell(
  target: FeatureTarget,
  verdict: FeatureCellWire['verdict'],
  extra: Partial<FeatureCellWire> = {},
): FeatureCellWire {
  return {
    package_name: target.package_name,
    version: target.version,
    verdict,
    data_status: 'COMPLETE',
    evidence_ids: [],
    note: null,
    reason_code: null,
    ...extra,
  }
}

/** 6행짜리 정상 결과. `over` 로 셀 하나씩 바꿔 시나리오를 만든다. */
function comparisonFor(
  targets: FeatureTarget[],
  over: Partial<FeatureComparisonResponse> = {},
  childLoggerVerdict: FeatureCellWire['verdict'] = 'SUPPORTED',
): FeatureComparisonResponse {
  const labels = [
    '구조화 JSON',
    'Child logger',
    '다중 출력 경로',
    '예외·거부 처리',
    '데이터 마스킹',
  ]
  return {
    data_status: 'COMPLETE',
    comparison_state: 'COMPLETE',
    packages: targets,
    environment: null,
    environment_note: null,
    features: labels.map((label, i) => ({
      feature_id: `f${i}`,
      feature_label: label,
      results: targets.map((t, j) =>
        cell(
          t,
          label === 'Child logger' && t.package_name === 'pino' ? childLoggerVerdict : 'SUPPORTED',
          {
            evidence_ids: [`E${String(i * 2 + j + 1).padStart(2, '0')}`],
          },
        ),
      ),
    })),
    narrative: [],
    narrative_error: null,
    evidence_count: 10,
    analyzed_at: '2026-09-02T09:24:00+09:00',
    ...over,
  }
}

beforeEach(() => {
  fetchFeatureVersions.mockReset()
  fetchFeatureComparison.mockReset()
  onOpenEvidence.mockReset()
  fetchFeatureVersions.mockImplementation(async (names: string[]) => versionsFor(names))
  fetchFeatureComparison.mockImplementation(async (targets: FeatureTarget[]) =>
    comparisonFor(targets),
  )
})

// 전역 자동 정리가 없다 — 남겨 두면 다음 시험에서 같은 문구가 둘로 잡힌다.
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const findTable = () => screen.findByRole('heading', { name: '핵심 기능 비교' })

describe('FeatureCompareTab', () => {
  it('패키지마다 최신 안정 버전이 골라져 있고 사용자가 아무것도 하지 않아도 분석이 시작된다', async () => {
    renderTab()

    await findTable()

    expect(fetchFeatureComparison).toHaveBeenCalledTimes(1)
    expect(fetchFeatureComparison).toHaveBeenCalledWith([
      { package_name: 'pino', version: '10.3.1' },
      { package_name: 'winston', version: '3.19.0' },
    ])
    expect(screen.getByLabelText('pino')).toHaveValue('10.3.1')
    expect(screen.getByLabelText('winston')).toHaveValue('3.19.0')
    expect(screen.getByText(/분석 완료 · 근거 10건 연결/)).toBeInTheDocument()
  })

  it('버전 드롭다운을 바꿔도 분석을 시작하지 않고 기존 결과를 둔 채 재분석 필요로 알린다', async () => {
    const user = userEvent.setup()
    renderTab()
    await findTable()

    await user.selectOptions(screen.getByLabelText('pino'), '10.2.0')

    expect(await screen.findByText(/재분석 필요 · 기존 결과 유지/)).toBeInTheDocument()
    expect(screen.getByText(/pino 10\.3\.1 → 10\.2\.0 변경됨/)).toBeInTheDocument()
    // 표는 그대로, 새 분석은 시작하지 않았다
    expect(screen.getByRole('heading', { name: '핵심 기능 비교' })).toBeInTheDocument()
    expect(fetchFeatureComparison).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: '선택한 버전으로 재분석' })).toBeEnabled()
  })

  it('재분석에 성공하면 결과를 바꾸고 직전 결과와 달라진 점을 한 번 보여준다', async () => {
    const user = userEvent.setup()
    renderTab()
    await findTable()
    fetchFeatureComparison.mockImplementationOnce(async (targets: FeatureTarget[]) =>
      comparisonFor(targets, {}, 'LIMITED_SUPPORT'),
    )

    await user.selectOptions(screen.getByLabelText('pino'), '10.2.0')
    await user.click(screen.getByRole('button', { name: '선택한 버전으로 재분석' }))

    expect(await screen.findByText(/재분석 완료 · 직전 결과와 달라진 점/)).toBeInTheDocument()
    expect(screen.getByText('Child logger · pino: 지원 → 제한적')).toBeInTheDocument()
    expect(screen.getByText('pino 10.3.1 → 10.2.0')).toBeInTheDocument()
    // 결과가 새 버전으로 바뀌었으니 재분석 필요 안내는 사라진다
    expect(screen.queryByText(/재분석 필요 · 기존 결과 유지/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '확인' }))
    expect(screen.queryByText(/재분석 완료 · 직전 결과와 달라진 점/)).not.toBeInTheDocument()
  })

  it('재분석에 실패하면 이전 결과를 그대로 두고 실패만 알린다', async () => {
    const user = userEvent.setup()
    renderTab()
    await findTable()
    fetchFeatureComparison.mockRejectedValueOnce(
      new ApiError(500, 'S001', '분석 서버에서 오류가 발생했습니다.'),
    )

    await user.selectOptions(screen.getByLabelText('winston'), '3.18.3')
    await user.click(screen.getByRole('button', { name: '선택한 버전으로 재분석' }))

    expect(
      await screen.findByText(/재분석에 실패했습니다 · 이전 결과를 유지했습니다/),
    ).toBeInTheDocument()
    expect(screen.getByText('분석 서버에서 오류가 발생했습니다.')).toBeInTheDocument()
    // 이전 결과의 열 머리글이 그대로다
    const table = screen.getByRole('table')
    expect(within(table).getByText('3.19.0')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeEnabled()
  })

  it('정식 버전이 없으면 사전 배포 버전을 고르지 않고 사용자의 선택을 기다린다', async () => {
    const user = userEvent.setup()
    fetchFeatureVersions.mockResolvedValue({
      packages: [
        {
          package_name: 'left-pad',
          latest_stable: null,
          versions: [{ version: '1.4.0-beta.2', prerelease: true }],
        },
      ],
    })
    renderTab(['left-pad'])

    expect(await screen.findByText('비교할 버전을 선택해 주세요')).toBeInTheDocument()
    expect(fetchFeatureComparison).not.toHaveBeenCalled()
    expect(screen.getByLabelText('left-pad')).toHaveValue('')
    expect(screen.getByRole('button', { name: '선택한 버전으로 분석' })).toBeDisabled()

    await user.selectOptions(screen.getByLabelText('left-pad'), '1.4.0-beta.2')
    await user.click(screen.getByRole('button', { name: '선택한 버전으로 분석' }))

    await waitFor(() =>
      expect(fetchFeatureComparison).toHaveBeenCalledWith([
        { package_name: 'left-pad', version: '1.4.0-beta.2' },
      ]),
    )
  })

  it('이 조합의 기능 비교가 없으면 고른 패키지를 적어 알리고 분석을 부르지 않는다', async () => {
    fetchFeatureVersions.mockRejectedValue(
      new ApiError(404, FEATURE_NOT_AVAILABLE, '이 조합의 기능 비교는 아직 준비되지 않았습니다.'),
    )
    renderTab()

    expect(await screen.findByText(/아직 준비되지 않았습니다/)).toBeInTheDocument()
    expect(screen.getByText('pino')).toBeInTheDocument()
    expect(fetchFeatureComparison).not.toHaveBeenCalled()
  })

  it('비교 가능한 기능이 부족하면 제한 안내를 붙이고, 환경·해설 데이터가 없으면 그 섹션을 그리지 않는다', async () => {
    fetchFeatureComparison.mockImplementation(async (targets: FeatureTarget[]) => {
      const full = comparisonFor(targets)
      return {
        ...full,
        comparison_state: 'COMPARISON_LIMITED',
        features: full.features.slice(0, 2),
      }
    })
    renderTab()

    expect(await screen.findByText('직접 비교 가능한 기능이 제한적입니다')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '핵심 비교 요약' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '기능 비교 해설' })).not.toBeInTheDocument()
  })

  it('환경 표와 해설이 있으면 그리고, 값이 없는 칸은 미확인으로 적는다', async () => {
    fetchFeatureComparison.mockImplementation(async (targets: FeatureTarget[]) =>
      comparisonFor(targets, {
        environment: [
          {
            key: 'node',
            label: 'Node.js',
            values: [
              { package_name: 'pino', value: '>=12' },
              { package_name: 'winston', value: null },
            ],
          },
        ],
        narrative: [
          { heading: '공통 기반', body: '두 패키지 모두 확인되었습니다.', evidence_ids: ['E01'] },
        ],
      }),
    )
    renderTab()

    expect(await screen.findByRole('heading', { name: '핵심 비교 요약' })).toBeInTheDocument()
    // 표 하단 고지에도 '미확인' 이 있어, 환경 표 안에서만 본다
    const environment = within(screen.getByRole('region', { name: '핵심 비교 요약' }))
    expect(environment.getByText('>=12')).toBeInTheDocument()
    expect(environment.getByText('미확인')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '기능 비교 해설' })).toBeInTheDocument()
    expect(screen.getByText('두 패키지 모두 확인되었습니다.')).toBeInTheDocument()
    expect(screen.getByText(/추천 · 순위 · 승자 표시는 제공하지 않습니다/)).toBeInTheDocument()
  })

  it('일시적 조회 실패로 미확인이 된 셀은 사유를 적고 다시 시도할 수 있다', async () => {
    const user = userEvent.setup()
    fetchFeatureComparison.mockImplementationOnce(async (targets: FeatureTarget[]) => {
      const full = comparisonFor(targets, { data_status: 'PARTIAL' })
      full.features[0].results[0] = cell(targets[0], 'UNCONFIRMED', {
        data_status: 'COLLECTION_ERROR',
        reason_code: 'TRANSIENT_FETCH_ERROR',
      })
      return full
    })
    renderTab()

    expect(await screen.findByText(/일부 완료 · 확인 가능한 결과 먼저 표시/)).toBeInTheDocument()
    expect(screen.getByText('일시적으로 자료를 받지 못함')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '다시 시도' }))

    await waitFor(() => expect(fetchFeatureComparison).toHaveBeenCalledTimes(2))
    await waitFor(() =>
      expect(screen.queryByText(/일부 완료 · 확인 가능한 결과 먼저 표시/)).not.toBeInTheDocument(),
    )
  })

  it('셀을 누르면 그 셀의 첫 근거 ID 로 근거 열기를 요청한다', async () => {
    const user = userEvent.setup()
    renderTab()
    await findTable()

    await user.click(screen.getByRole('button', { name: '구조화 JSON pino 지원 — 근거 열기' }))

    expect(onOpenEvidence).toHaveBeenCalledWith('E01')
  })
})
