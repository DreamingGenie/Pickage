import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  FeatureRunErrorCode,
  FeatureRunResponse,
  FeatureTarget,
  PackagesOverviewResponse,
  PackageEnvResponse,
  RagComparisonResult,
} from '@/api/types'
import { useAnalysisRun } from '@/routes/report/_components/use-analysis-run'
import { FeatureCompareTab } from '@/routes/report/features/feature-compare-tab'

const { fetchPackagesOverview, fetchPackageEnv, startFeatureRun, fetchFeatureRun } = vi.hoisted(
  () => ({
    fetchPackagesOverview: vi.fn(),
    fetchPackageEnv: vi.fn(),
    startFeatureRun: vi.fn(),
    fetchFeatureRun: vi.fn(),
  }),
)

// 실제 mock 데이터·지연 대신 endpoints 경계에서 직접 목한다 — 시나리오를 결정적으로 구성한다.
vi.mock('@/api/endpoints', () => ({
  USE_MOCK: false,
  fetchPackagesOverview,
  fetchPackageEnv,
  startFeatureRun,
  fetchFeatureRun,
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

const LATEST: Record<string, string> = { pino: '10.3.1', winston: '3.19.0' }

/**
 * 버전은 개요(`GET /api/packages`)의 `latest_version` 에서 온다 — 고를 수 있는 버전을 주는
 * endpoint 가 아직 없어서다. 지표 필드는 이 화면이 읽지 않으므로 null 로 둔다.
 */
function overviewFor(names: string[]): PackagesOverviewResponse {
  return {
    snapshot_at: '2026-08-31',
    items: names.map((name) => ({
      name,
      repo_url: null,
      latest_version: LATEST[name],
      published_at: '2026-08-01T00:00:00Z',
      description: null,
      licenses: [],
      is_deprecated: false,
      downloads: null,
      stars: null,
      stars_delta: null,
      open_issues: null,
      open_issues_delta: null,
    })),
    not_found: [],
  }
}

/** `package_env` 응답. AI 실행과 무관한 단순 조회다. */
function envFor(targets: FeatureTarget[]): PackageEnvResponse {
  return {
    items: targets.map((t, i) => ({
      name: t.package_name,
      version: t.version,
      module_format: i === 0 ? 'CJS' : 'ESM_CJS',
      types_bundled: i === 0,
      direct_dependencies: i === 0 ? 3 : null,
      peer_dependencies: 0,
    })),
    not_found: [],
  }
}

/** RAG 응답 원본. **여기만 camelCase 다**(계약의 주인이 `ai/rag/main.py`). */
function ragResult(targets: FeatureTarget[]): RagComparisonResult {
  const labels = ['구조화 JSON', 'Child logger', '다중 출력 경로']
  return {
    dataStatus: 'COMPLETE',
    packages: targets.map((t) => ({ package: t.package_name, version: t.version })),
    features: labels.map((featureLabel, i) => ({
      featureLabel,
      results: targets.map((t, j) => ({
        package: t.package_name,
        version: t.version,
        verdict: 'SUPPORTED' as const,
        evidenceIds: [`E${String(i * 2 + j + 1).padStart(2, '0')}`],
        groundedIn: 'EVIDENCE' as const,
        note: null,
      })),
    })),
    narrative: [{ heading: '공통 기반', body: '두 패키지 모두 확인되었습니다.', evidenceIds: [] }],
    narrativeError: null,
    sources: targets.map((t) => ({
      package: t.package_name,
      version: t.version,
      status: 'OK' as const,
      readmeBytes: 4096,
      proseChars: 2048,
    })),
  }
}

function runResponse(over: Partial<FeatureRunResponse> = {}): FeatureRunResponse {
  return {
    run_id: 'run-1',
    status: 'RUNNING',
    phase: 'PREPARING_DOCS',
    refs: ['pino@10.3.1', 'winston@3.19.0'],
    elapsed_sec: 0,
    result: null,
    error_code: null,
    error_detail: null,
    ...over,
  }
}

const TARGETS: FeatureTarget[] = [
  { package_name: 'pino', version: '10.3.1' },
  { package_name: 'winston', version: '3.19.0' },
]

/** 완료 응답을 돌려주는 폴링. 시작 → 첫 조회에서 끝난다. */
function completesWith(result = ragResult(TARGETS)) {
  startFeatureRun.mockResolvedValue(runResponse())
  fetchFeatureRun.mockResolvedValue(runResponse({ status: 'COMPLETED', phase: 'DONE', result }))
}

function failsWith(code: FeatureRunErrorCode) {
  startFeatureRun.mockResolvedValue(runResponse())
  fetchFeatureRun.mockResolvedValue(runResponse({ status: 'FAILED', error_code: code }))
}

beforeEach(() => {
  fetchPackagesOverview.mockReset()
  fetchPackageEnv.mockReset()
  startFeatureRun.mockReset()
  fetchFeatureRun.mockReset()
  onOpenEvidence.mockReset()
  fetchPackagesOverview.mockImplementation(async (names: string[]) => overviewFor(names))
  fetchPackageEnv.mockImplementation(async (targets: FeatureTarget[]) => envFor(targets))
})

// 전역 자동 정리가 없다 — 남겨 두면 다음 시험에서 같은 문구가 둘로 잡힌다.
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const startButton = () => screen.getByRole('button', { name: '기능 비교 시작' })

describe('FeatureCompareTab', () => {
  it('소비 조건 표는 버전을 고르는 즉시 뜨고, AI 분석은 저절로 시작하지 않는다', async () => {
    completesWith()
    renderTab()

    const summary = within(await screen.findByRole('region', { name: '핵심 비교 요약' }))
    expect(summary.getByText('CommonJS')).toBeInTheDocument()
    expect(summary.getByText('ESM + CommonJS')).toBeInTheDocument()
    // null 은 0 이 아니라 모름이다 — 0개로 적지 않는다
    expect(summary.getByText('미확인')).toBeInTheDocument()
    expect(screen.getByLabelText('pino')).toHaveValue('10.3.1')

    expect(startFeatureRun).not.toHaveBeenCalled()
    expect(startButton()).toBeEnabled()
  })

  it('버튼을 누르면 로딩을 보여 주고, 끝나면 그 자리에 결과가 뜬다', async () => {
    const user = userEvent.setup()
    let release: (value: FeatureRunResponse) => void = () => {}
    startFeatureRun.mockReturnValue(
      new Promise<FeatureRunResponse>((resolve) => {
        release = resolve
      }),
    )
    fetchFeatureRun.mockResolvedValue(
      runResponse({ status: 'COMPLETED', phase: 'DONE', result: ragResult(TARGETS) }),
    )
    renderTab()

    await user.click(await screen.findByRole('button', { name: '기능 비교 시작' }))

    expect(await screen.findByText(/README 를 모으고 있습니다/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '핵심 기능 비교' })).not.toBeInTheDocument()
    // 확인된 사실은 생성을 기다리지 않는다 — 위 표는 그대로 보인다
    expect(screen.getByRole('region', { name: '핵심 비교 요약' })).toBeInTheDocument()

    release(runResponse())

    expect(await screen.findByRole('heading', { name: '핵심 기능 비교' })).toBeInTheDocument()
    expect(screen.getByText('두 패키지 모두 확인되었습니다.')).toBeInTheDocument()
    await waitFor(() =>
      expect(startFeatureRun).toHaveBeenCalledWith([
        { package_name: 'pino', version: '10.3.1' },
        { package_name: 'winston', version: '3.19.0' },
      ]),
    )
    expect(screen.getByRole('button', { name: '선택한 버전으로 재분석' })).toBeEnabled()
  })

  it('근거를 확인하지 못해 실패하면 다시 시도할 수 있다고 말하지 않는다', async () => {
    const user = userEvent.setup()
    failsWith('VERIFICATION_FAILED')
    renderTab()

    await user.click(await screen.findByRole('button', { name: '기능 비교 시작' }))

    expect(
      await screen.findByText(/판정의 근거를 확인하지 못해 결과를 내지 않았습니다/),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '다시 시도' })).not.toBeInTheDocument()
    // 실패해도 확인된 소비 조건은 그대로 남는다
    expect(screen.getByRole('region', { name: '핵심 비교 요약' })).toBeInTheDocument()
  })

  it('문헌을 아직 못 받아 실패하면 다시 시도할 수 있다', async () => {
    const user = userEvent.setup()
    failsWith('DOC_NOT_FOUND')
    renderTab()

    await user.click(await screen.findByRole('button', { name: '기능 비교 시작' }))

    expect(await screen.findByText(/이 버전의 문헌을 아직 받지 못했습니다/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeEnabled()
  })

  it('카탈로그에 이름이 하나도 없으면 고른 패키지를 적어 알리고 아무것도 부르지 않는다', async () => {
    fetchPackagesOverview.mockResolvedValue({
      snapshot_at: null,
      items: [],
      not_found: ['pino', 'winston'],
    })
    renderTab()

    expect(await screen.findByText(/아직 준비되지 않았습니다/)).toBeInTheDocument()
    expect(screen.getByText('pino')).toBeInTheDocument()
    expect(fetchPackageEnv).not.toHaveBeenCalled()
    expect(startFeatureRun).not.toHaveBeenCalled()
  })

  /**
   * 일부만 없는 경우는 전체를 막지 않는다 — 찾은 패키지의 소비 조건은 그대로 보여 준다.
   * 없는 이름은 버전을 정할 수 없어 비교 대상에서 빠진다.
   */
  it('일부 이름만 없으면 나머지로 계속한다', async () => {
    fetchPackagesOverview.mockImplementation(async () => {
      const full = overviewFor(['pino', 'winston'])
      return { ...full, items: full.items.slice(0, 1), not_found: ['winston'] }
    })
    completesWith()
    renderTab()

    expect(await screen.findByRole('region', { name: '핵심 비교 요약' })).toBeInTheDocument()
    await waitFor(() =>
      expect(fetchPackageEnv).toHaveBeenCalledWith([{ package_name: 'pino', version: '10.3.1' }]),
    )
  })

  it('셀을 누르면 그 셀의 첫 근거 ID 로 근거 열기를 요청한다', async () => {
    const user = userEvent.setup()
    completesWith()
    renderTab()

    await user.click(await screen.findByRole('button', { name: '기능 비교 시작' }))
    await screen.findByRole('heading', { name: '핵심 기능 비교' })

    await user.click(screen.getByRole('button', { name: '구조화 JSON pino 지원 — 근거 열기' }))

    expect(onOpenEvidence).toHaveBeenCalledWith('E01')
  })
})
