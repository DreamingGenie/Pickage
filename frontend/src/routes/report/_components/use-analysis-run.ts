import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react'

import { ApiError, errorNotice } from '@/api/client'
import { USE_MOCK } from '@/api/endpoints'
import { useFeatureComparisonRun, useFeatureVersions } from '@/api/queries'
import { FEATURE_NOT_AVAILABLE, type FeatureTarget } from '@/api/types'
import {
  adaptComparison,
  adaptVersions,
  diffAnalyses,
  isEmptyChange,
} from '@/routes/report/features/adapter'
import type { ChangeSummary, ComparisonView, PackageVersions } from '@/routes/report/features/model'

/**
 * 기능 분석 실행 상태 (구상안 §9, S15P21A506-217).
 *
 * <h2>무엇을 들고 있나</h2>
 *
 * - 패키지별 **선택한 버전**(드롭다운)과 **완료된 결과의 버전**. 둘이 다르면 `재분석 필요`
 *   이고 PDF 는 막힌다(§9.2, §13.2). 기존 완료 결과는 그대로 유지한다.
 * - 직전 완료 결과. 재분석이 성공하면 클라이언트에서 새 결과와 비교해 변경점을 만든다(§9.5).
 *   서버는 판정을 저장하지 않으므로(`DEC-FEATURE-CACHE-20260917-01`) 새로고침하면 사라진다.
 * - 실패하면 이전 완료 결과를 그대로 둔다. 성공해야만 결과 포인터가 바뀐다(§9.3).
 *
 * <h2>진행 단계</h2>
 *
 * 완료되지 않은 단계를 완료로 보내지 않는다. 분석 API 가 단계를 알려주는 방식(SSE)은
 * 아직 없으므로 **실제 진행은 알 수 없다** — 그래서 mock 개발 모드에서만 시간에 따라
 * 단계를 흉내 내 화면 상태를 확인한다. 그 밖에는 끝날 때까지 0단계로 두고 결과가 오면 한
 * 번에 완료로 바꾼다. SSE 가 붙으면 `PROGRESS` 를 서버 이벤트로 바꾼다.
 */
export const RUN_STEPS = [
  { key: 'VERSION_VERIFIED', label: '정확한 버전 확인' },
  { key: 'ARTIFACT_COLLECTED', label: '배포본 수집 · 무결성 검증' },
  { key: 'ENVIRONMENT_EXTRACTED', label: '환경 · 설치 조건 추출' },
  { key: 'EVIDENCE_EXTRACTED', label: '근거 추출' },
  { key: 'ASSESSMENTS_LINKED', label: '판정 연결' },
  { key: 'NARRATIVE_GENERATED', label: '중립 해설 생성' },
] as const

/**
 * - `IDLE`: 아직 시작하지 않음(정식 버전이 없어 사용자의 선택을 기다림)
 * - `RUNNING`: 버전 목록을 받는 중이거나 분석 중. 재분석 중에도 이전 결과가 있으면 그대로 보인다
 * - `COMPLETED`: 완료된 결과가 있고 실행 중이 아님
 * - `FAILED`: 결과가 하나도 없는데 실패함
 * - `UNAVAILABLE`: 이 조합의 기능 비교가 아직 없음
 */
export type RunStatus = 'IDLE' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'UNAVAILABLE'

export interface AnalysisRun {
  status: RunStatus
  /** 완료된 단계 수. RUN_STEPS 앞에서부터 채워진다. */
  doneCount: number
  /** 시작 후 흐른 초 */
  elapsedSec: number
  /** 한 번이라도 완료된 적이 있는지. 재분석 중에도 이전 결과를 계속 보여주려면 필요하다. */
  hasCompletedOnce: boolean
  /**
   * run이 바뀔 때마다(=재분석 시작) 값이 바뀌는 식별자.
   * PDF 모달이 이 값을 감시해, 재분석이 시작되면 이전 COMPLETE 파일을 버린다(S15P21A506-220).
   */
  runId: number
  /** 선택한 버전이 완료 결과의 버전과 다르다. 기존 결과는 유지하고 PDF 만 막는다(§9.2). */
  reanalysisRequired: boolean
  /** 선택한 버전으로 새 run 시작. 성공해야만 결과 포인터가 바뀐다(구상안 9.3). */
  restart: () => void
}

export interface FeatureFailure {
  message: string
  /** 다시 해 볼 값어치가 있는지 — 규칙을 어긴 요청은 같은 결과다 */
  retryable: boolean
  /** 버전 목록을 못 받았는지, 분석 실행이 실패했는지 */
  kind: 'VERSIONS' | 'RUN'
}

export interface FeatureAnalysis extends AnalysisRun {
  /** 버전 목록. 아직 못 받았으면 null */
  versions: PackageVersions[] | null
  /** 패키지별 현재 선택. 고를 수 없으면(정식 버전 없음) null */
  selected: Record<string, string | null>
  select: (name: string, version: string) => void
  /** 지금 화면에 보이는 완료 결과 */
  completed: ComparisonView | null
  /** 재분석이 성공한 직후 한 번 보여주는 변경점 */
  changes: ChangeSummary | null
  dismissChanges: () => void
  /** 마지막 시도의 실패. 이전 결과가 있으면 그 결과는 유지된 채로 이것만 알린다 */
  failure: FeatureFailure | null
  /** `선택한 버전으로 재분석` 을 누를 수 있는지 */
  canStart: boolean
  retryVersions: () => void
}

/** mock 개발 모드에서만 쓰는 단계별 소요 시간 흉내. 근거 추출이 제일 오래 걸린다. */
const STEP_MS = [400, 800, 500, 1600, 600, 900]

interface State {
  /** 이 상태가 어느 비교 대상 조합의 것인지. 조합이 바뀌면 통째로 버린다 */
  key: string
  picks: Record<string, string>
  completed: ComparisonView | null
  changes: ChangeSummary | null
  runId: number
  running: boolean
  failed: string | null
  /** 응답은 왔지만 진행 흉내가 끝나기 전(mock 에서만 생긴다) */
  arrived: { runId: number; view: ComparisonView } | null
  doneCount: number
  elapsedSec: number
}

type Action =
  | { type: 'RESET'; key: string }
  | { type: 'PICK'; name: string; version: string }
  | { type: 'START'; runId: number }
  | { type: 'ARRIVED'; runId: number; view: ComparisonView }
  | { type: 'COMMIT' }
  | { type: 'FAILED'; runId: number; message: string }
  | { type: 'PROGRESS'; doneCount: number }
  | { type: 'TICK'; elapsedSec: number }
  | { type: 'DISMISS_CHANGES' }

const initial = (key: string): State => ({
  key,
  picks: {},
  completed: null,
  changes: null,
  runId: 0,
  running: false,
  failed: null,
  arrived: null,
  doneCount: 0,
  elapsedSec: 0,
})

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'RESET':
      return initial(action.key)
    case 'PICK':
      return { ...state, picks: { ...state.picks, [action.name]: action.version } }
    case 'START':
      return {
        ...state,
        runId: action.runId,
        running: true,
        failed: null,
        arrived: null,
        doneCount: 0,
        elapsedSec: 0,
        // 새 분석을 시작하면 지난 변경점 안내는 거둔다
        changes: null,
      }
    case 'ARRIVED':
      if (action.runId !== state.runId) return state
      return { ...state, arrived: { runId: action.runId, view: action.view } }
    case 'COMMIT': {
      if (!state.arrived) return state
      const next = state.arrived.view
      const diff = state.completed ? diffAnalyses(state.completed, next) : null
      return {
        ...state,
        completed: next,
        changes: diff && !isEmptyChange(diff) ? diff : null,
        running: false,
        failed: null,
        arrived: null,
        doneCount: RUN_STEPS.length,
      }
    }
    case 'FAILED':
      if (action.runId !== state.runId) return state
      // 이전 완료 결과는 건드리지 않는다 — 성공해야만 바뀐다(§9.3)
      return { ...state, running: false, failed: action.message, arrived: null }
    case 'PROGRESS':
      return { ...state, doneCount: Math.max(state.doneCount, action.doneCount) }
    case 'TICK':
      return { ...state, elapsedSec: action.elapsedSec }
    case 'DISMISS_CHANGES':
      return { ...state, changes: null }
  }
}

export function useAnalysisRun(names: readonly string[]): FeatureAnalysis {
  const key = names.join(',')
  const [state, dispatch] = useReducer(reducer, key, initial)
  const runSeq = useRef(0)
  const autoStartedFor = useRef<string | null>(null)

  // 비교 대상이 바뀌면 이전 조합의 선택·결과를 통째로 버린다. 렌더 중 dispatch 는 React 가
  // 곧바로 다시 그리므로 낡은 값이 화면에 나가지 않는다.
  if (state.key !== key) dispatch({ type: 'RESET', key })

  const versionsQuery = useFeatureVersions(names)
  const comparison = useFeatureComparisonRun()
  const runComparison = comparison.mutateAsync

  const versions = useMemo(
    () => (versionsQuery.data ? adaptVersions(versionsQuery.data) : null),
    [versionsQuery.data],
  )

  const unavailable =
    versionsQuery.error instanceof ApiError && versionsQuery.error.code === FEATURE_NOT_AVAILABLE

  /** 선택 = 사용자가 고른 값, 없으면 최신 안정 버전. 정식 버전이 없으면 null(자동 선택 금지). */
  const selected = useMemo(() => {
    const out: Record<string, string | null> = {}
    for (const name of names) {
      const latest = versions?.find((v) => v.name === name)?.latestStable ?? null
      out[name] = state.picks[name] ?? latest
    }
    return out
  }, [names, versions, state.picks])

  const targets = useMemo<FeatureTarget[] | null>(() => {
    if (!versions) return null
    const list: FeatureTarget[] = []
    for (const name of names) {
      const version = selected[name]
      if (!version) return null
      list.push({ package_name: name, version })
    }
    return list.length > 0 ? list : null
  }, [names, versions, selected])

  const start = useCallback(
    (list: FeatureTarget[]) => {
      const id = ++runSeq.current
      dispatch({ type: 'START', runId: id })
      runComparison(list).then(
        (response) => dispatch({ type: 'ARRIVED', runId: id, view: adaptComparison(response) }),
        (error) => dispatch({ type: 'FAILED', runId: id, message: errorNotice(error).message }),
      )
    },
    [runComparison],
  )

  // 최초 진입: 모든 패키지에 최신 안정 버전이 있으면 사용자가 아무것도 하지 않아도 시작한다(§9.1).
  // 정식 버전이 없는 패키지가 있으면 시작하지 않는다 — 사전 배포 버전을 대신 고르지 않는다.
  const allDefaulted =
    versions !== null && names.every((n) => versions.find((v) => v.name === n)?.latestStable)
  useEffect(() => {
    if (!targets || !allDefaulted || autoStartedFor.current === key) return
    autoStartedFor.current = key
    start(targets)
  }, [targets, allDefaulted, key, start])

  // 진행 표시. 실제 단계는 알 수 없으므로 흉내는 mock 개발 모드에서만 낸다.
  useEffect(() => {
    if (!state.running) return
    const startedAt = Date.now()
    const timers: number[] = []
    if (USE_MOCK) {
      let acc = 0
      STEP_MS.forEach((ms, i) => {
        acc += ms
        timers.push(window.setTimeout(() => dispatch({ type: 'PROGRESS', doneCount: i + 1 }), acc))
      })
    }
    const tick = window.setInterval(
      () => dispatch({ type: 'TICK', elapsedSec: Math.floor((Date.now() - startedAt) / 1000) }),
      1000,
    )
    return () => {
      timers.forEach(clearTimeout)
      clearInterval(tick)
    }
  }, [state.running, state.runId])

  // 응답이 왔고 진행 표시도 끝났으면 결과를 바꾼다.
  const progressDone = !USE_MOCK || state.doneCount >= RUN_STEPS.length
  useEffect(() => {
    if (state.running && state.arrived?.runId === state.runId && progressDone) {
      dispatch({ type: 'COMMIT' })
    }
  }, [state.running, state.arrived, state.runId, progressDone])

  const restart = useCallback(() => {
    if (!targets || state.running) return
    start(targets)
  }, [targets, state.running, start])

  const select = useCallback(
    (name: string, version: string) => dispatch({ type: 'PICK', name, version }),
    [],
  )
  const dismissChanges = useCallback(() => dispatch({ type: 'DISMISS_CHANGES' }), [])
  const retryVersions = useCallback(() => void versionsQuery.refetch(), [versionsQuery])

  const completedVersions = state.completed?.packages
  const reanalysisRequired =
    completedVersions !== undefined &&
    completedVersions.some((p) => selected[p.name] != null && selected[p.name] !== p.version)

  const versionsFailed = versionsQuery.isError && !unavailable
  const status: RunStatus = unavailable
    ? 'UNAVAILABLE'
    : versionsQuery.isLoading || state.running
      ? 'RUNNING'
      : state.completed
        ? 'COMPLETED'
        : versionsFailed || state.failed
          ? 'FAILED'
          : 'IDLE'

  let failure: FeatureFailure | null = null
  if (versionsFailed) {
    const notice = errorNotice(versionsQuery.error)
    failure = { message: notice.message, retryable: notice.retryable, kind: 'VERSIONS' }
  } else if (state.failed) {
    failure = { message: state.failed, retryable: true, kind: 'RUN' }
  }

  return {
    status,
    doneCount: state.doneCount,
    elapsedSec: state.elapsedSec,
    hasCompletedOnce: state.completed !== null,
    runId: state.runId,
    reanalysisRequired,
    restart,
    versions,
    selected,
    select,
    completed: state.completed,
    changes: state.changes,
    dismissChanges,
    failure,
    canStart:
      targets !== null && !state.running && (state.completed === null || reanalysisRequired),
    retryVersions,
  }
}
