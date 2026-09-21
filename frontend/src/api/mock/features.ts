/**
 * 기능 비교 mock (S15P21A506-217).
 *
 * 값은 와이어프레임(기능 비교 · 상태 · Evidence Drawer, 2026-09)을 옮긴 **개발용 화면 확인
 * 자료**다. 분석 결과가 아니므로 `VITE_USE_MOCK=true` 일 때만 쓰인다. 실제 배포에서 사용자가
 * 보는 예시는 구상안 16장 POC 실측(`api/poc-features.ts`)이다.
 *
 * 난수도 실제 시계도 쓰지 않는다 — 새로고침·테스트에서 항상 같은 결과가 나와야 한다
 * (기존 mock 관례).
 *
 * 개발 중 화면을 확인할 때 쓰는 이름:
 * - `pino` `winston` `bunyan` — 소비 조건이 실제 `package_env` 값으로 찬다
 * - `left-pad` — 정식 버전이 없다. 사전 배포 버전만 있어 자동 선택이 일어나지 않는다
 * - 그 외 이름 — 버전 목록은 나오고, 소비 조건은 `not_found` 로 빠진다
 */

import { ApiError } from '@/api/client'
import type {
  FeatureRunResponse,
  FeatureVerdict,
  PackageEnvItemWire,
  PackageEnvResponse,
  RagComparisonResult,
} from '@/api/types'

const LATENCY_MS = 350
const delay = <T>(value: T): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS))

/** 알려진 패키지의 버전 목록. 첫 항목이 최신 안정 버전이다. */
/* ------------------------------------------------------------------ *
 * 기능 비교 결과
 * ------------------------------------------------------------------ */

/**
 * RAG 원본 모양의 결과. **camelCase 다** — 백엔드가 이 값을 옮기지 않고 그대로 통과시킨다.
 * mock 도 같은 모양이라야 화면이 실서버와 같은 코드로 읽는다.
 */
function mockRagResult(refs: readonly string[]): RagComparisonResult {
  const packages = refs.map((ref) => {
    const at = ref.lastIndexOf('@')
    return { package: ref.slice(0, at), version: ref.slice(at + 1) }
  })
  return {
    dataStatus: 'COMPLETE',
    packages,
    features: [
      {
        featureLabel: '구조적 로깅(JSON)',
        results: packages.map((p) => ({
          package: p.package,
          version: p.version,
          verdict: 'SUPPORTED' as FeatureVerdict,
          evidenceIds: ['E01'],
          groundedIn: 'EVIDENCE' as const,
          note: null,
        })),
      },
      {
        featureLabel: '로그 레벨 사용자 정의',
        results: packages.map((p, i) => ({
          package: p.package,
          version: p.version,
          verdict: (i === 0 ? 'SUPPORTED' : 'UNCONFIRMED') as FeatureVerdict,
          evidenceIds: i === 0 ? ['E02'] : [],
          groundedIn: 'EVIDENCE' as const,
          note: i === 0 ? null : '확인한 자료에서 발견되지 않음',
        })),
      },
    ],
    narrative: [
      {
        heading: '무엇이 다른가',
        body: '세 패키지 모두 JSON 로그를 낸다. 레벨 사용자 정의는 winston 에서만 확인됐다.',
        evidenceIds: ['E01', 'E02'],
      },
    ],
    narrativeError: null,
    sources: packages.map((p) => ({
      package: p.package,
      version: p.version,
      status: 'OK' as const,
      readmeBytes: 8_192,
      proseChars: 2_400,
    })),
  }
}

/* ------------------------------------------------------------------ *
 * 소비 조건 · run (BE S15P21A506-130 계약)
 * ------------------------------------------------------------------ */

/**
 * 실제 `package_env` 에서 확인한 값이다. 지어낸 값을 두면 화면 문구가 맞는지 판단할 수 없다.
 * bunyan 이 타입 미동봉인 것은 구상안 16장 POC 와도 일치한다.
 */
const MOCK_ENV: Record<string, PackageEnvItemWire> = {
  'winston@3.19.0': {
    name: 'winston',
    version: '3.19.0',
    module_format: 'CJS',
    types_bundled: true,
    direct_dependencies: 11,
    peer_dependencies: 0,
  },
  'pino@10.3.1': {
    name: 'pino',
    version: '10.3.1',
    module_format: 'CJS',
    types_bundled: true,
    direct_dependencies: 11,
    peer_dependencies: 0,
  },
  'bunyan@1.8.15': {
    name: 'bunyan',
    version: '1.8.15',
    module_format: 'CJS',
    types_bundled: false,
    direct_dependencies: 4,
    peer_dependencies: 0,
  },
  // 듀얼과 ESM 전용, 그리고 unpublish(개수 null) 를 한 번씩 밟게 둔다 — 화면이 셋을
  // 다르게 그리는지 mock 에서 확인할 수 있어야 한다.
  '@babel/core@8.0.1': {
    name: '@babel/core',
    version: '8.0.1',
    module_format: 'ESM_ONLY',
    types_bundled: false,
    direct_dependencies: 16,
    peer_dependencies: 0,
  },
  'chalk@5.6.1': {
    name: 'chalk',
    version: '5.6.1',
    module_format: 'UNKNOWN',
    types_bundled: false,
    direct_dependencies: null,
    peer_dependencies: null,
  },
}

export function mockPackageEnv(refs: readonly string[]): Promise<PackageEnvResponse> {
  const items = refs
    .map((ref) => MOCK_ENV[ref])
    .filter((item): item is PackageEnvItemWire => !!item)
  const notFound = refs.filter((ref) => !MOCK_ENV[ref])
  return delay({ items, not_found: notFound })
}

/** run 상태를 메모리에 들고 흉내 낸다. 두 번째 조회부터 끝난 것으로 본다. */
const MOCK_RUNS = new Map<string, { refs: string[]; polls: number }>()

export function mockStartFeatureRun(refs: readonly string[]): Promise<FeatureRunResponse> {
  const runId = `mock-${Date.now()}`
  MOCK_RUNS.set(runId, { refs: [...refs], polls: 0 })
  return delay({
    run_id: runId,
    status: 'RUNNING',
    phase: 'PREPARING_DOCS',
    refs: [...refs],
    elapsed_sec: 0,
    result: null,
    error_code: null,
    error_detail: null,
  })
}

export function mockFeatureRun(runId: string): Promise<FeatureRunResponse> {
  const run = MOCK_RUNS.get(runId)
  if (!run) {
    return Promise.reject(new ApiError(404, 'C006', '요청한 리소스를 찾을 수 없음'))
  }
  run.polls += 1
  if (run.polls < 2) {
    return delay({
      run_id: runId,
      status: 'RUNNING',
      phase: 'COMPARING',
      refs: run.refs,
      elapsed_sec: run.polls * 2,
      result: null,
      error_code: null,
      error_detail: null,
    })
  }
  return delay({
    run_id: runId,
    status: 'COMPLETED',
    phase: 'DONE',
    refs: run.refs,
    elapsed_sec: run.polls * 2,
    result: mockRagResult(run.refs),
    error_code: null,
    error_detail: null,
  })
}
