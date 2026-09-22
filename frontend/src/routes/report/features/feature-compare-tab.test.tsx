import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  FeatureRunErrorCode,
  FeatureRunResponse,
  FeatureTarget,
  FeatureVersionsResponse,
  PackageEnvResponse,
  RagComparisonResult,
} from '@/api/types'
import { useAnalysisRun } from '@/routes/report/_components/use-analysis-run'
import { FeatureCompareTab } from '@/routes/report/features/feature-compare-tab'

const { fetchFeatureVersions, fetchPackageEnv, startFeatureRun, fetchFeatureRun } = vi.hoisted(
  () => ({
    fetchFeatureVersions: vi.fn(),
    fetchPackageEnv: vi.fn(),
    startFeatureRun: vi.fn(),
    fetchFeatureRun: vi.fn(),
  }),
)

// 실제 mock 데이터·지연 대신 endpoints 경계에서 직접 목한다 — 시나리오를 결정적으로 구성한다.
vi.mock('@/api/endpoints', () => ({
  USE_MOCK: false,
  fetchFeatureVersions,
  fetchPackageEnv,
  startFeatureRun,
  fetchFeatureRun,
}))

const NAMES = ['pino', 'winston']

function Harness({ names = NAMES }: { names?: string[] }) {
  const run = useAnalysisRun(names)
  return <FeatureCompareTab packages={names} run={run} />
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
  pino: ['10.3.1', '10.2.0', '10.1.0'],
  winston: ['3.19.0', '3.18.3', '3.18.0'],
}

/** 버전 목록. 서버처럼 최신순 최대 3개, 맨 앞이 기본값이다. */
function versionsFor(names: string[]): FeatureVersionsResponse {
  return {
    packages: names.map((name) => ({
      package_name: name,
      latest_stable: VERSIONS[name][0],
      versions: VERSIONS[name],
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
  fetchFeatureVersions.mockReset()
  fetchPackageEnv.mockReset()
  startFeatureRun.mockReset()
  fetchFeatureRun.mockReset()
  fetchFeatureVersions.mockImplementation(async (names: string[]) => versionsFor(names))
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

    const summary = within(await screen.findByRole('region', { name: '설치하기 전에 알아 둘 것' }))
    expect(summary.getByText('require (CommonJS)')).toBeInTheDocument()
    expect(summary.getByText('import · require 둘 다')).toBeInTheDocument()
    // null 은 0 이 아니라 모름이다 — 0개로 적지 않는다
    expect(summary.getByText('알 수 없음')).toBeInTheDocument()
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
    expect(screen.getByRole('region', { name: '설치하기 전에 알아 둘 것' })).toBeInTheDocument()

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
    expect(screen.getByRole('region', { name: '설치하기 전에 알아 둘 것' })).toBeInTheDocument()
  })

  it('문헌을 아직 못 받아 실패하면 다시 시도할 수 있다', async () => {
    const user = userEvent.setup()
    failsWith('DOC_NOT_FOUND')
    renderTab()

    await user.click(await screen.findByRole('button', { name: '기능 비교 시작' }))

    expect(await screen.findByText(/이 버전의 문헌을 아직 받지 못했습니다/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeEnabled()
  })

  it('드롭다운에 서버가 준 버전이 뜨고, 바꾸면 소비 조건을 그 버전으로 다시 묻는다', async () => {
    const user = userEvent.setup()
    completesWith()
    renderTab()

    const picker = await screen.findByLabelText('pino')
    expect(
      within(picker)
        .getAllByRole('option')
        .map((o) => o.getAttribute('value')),
    ).toEqual(['10.3.1', '10.2.0', '10.1.0'])

    await user.selectOptions(picker, '10.2.0')

    await waitFor(() =>
      expect(fetchPackageEnv).toHaveBeenLastCalledWith([
        { package_name: 'pino', version: '10.2.0' },
        { package_name: 'winston', version: '3.19.0' },
      ]),
    )
    // AI 비교는 저절로 돌지 않는다
    expect(startFeatureRun).not.toHaveBeenCalled()
  })

  it('고를 버전이 없는 패키지는 그 사실을 적고 시작 버튼을 막는다', async () => {
    fetchFeatureVersions.mockResolvedValue({
      packages: [
        { package_name: 'pino', latest_stable: '10.3.1', versions: ['10.3.1'] },
        { package_name: 'winston', latest_stable: null, versions: [] },
      ],
      not_found: [],
    })
    renderTab()

    expect(await screen.findByText('비교할 수 있는 버전이 아직 없어요.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '기능 비교 시작' })).toBeDisabled()
  })

  it('카탈로그에 이름이 하나도 없으면 고른 패키지를 적어 알리고 아무것도 부르지 않는다', async () => {
    fetchFeatureVersions.mockResolvedValue({ packages: [], not_found: ['pino', 'winston'] })
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
    fetchFeatureVersions.mockImplementation(async () => {
      const full = versionsFor(['pino', 'winston'])
      return { packages: full.packages.slice(0, 1), not_found: ['winston'] }
    })
    completesWith()
    renderTab()

    expect(
      await screen.findByRole('region', { name: '설치하기 전에 알아 둘 것' }),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(fetchPackageEnv).toHaveBeenCalledWith([{ package_name: 'pino', version: '10.3.1' }]),
    )
  })

  /** 출처 표기와 근거 Drawer 는 뺐다(기획 협의). 칸은 눌리는 버튼이 아니다. */
  it('결과 칸은 판정만 보여 주고 출처를 열지 않는다', async () => {
    const user = userEvent.setup()
    completesWith()
    renderTab()

    await user.click(await screen.findByRole('button', { name: '기능 비교 시작' }))
    await screen.findByRole('heading', { name: '핵심 기능 비교' })

    expect(screen.queryByRole('button', { name: /근거 열기|출처 열기/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/출처/)).not.toBeInTheDocument()
  })
})
