import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'

import { errorNotice } from '@/api/client'
import { useFeatureRun, useFeatureVersions, useStartFeatureRun } from '@/api/queries'
import type { FeatureRunErrorCode, FeatureRunPhase, FeatureTarget } from '@/api/types'
import { diffAnalyses, isEmptyChange } from '@/routes/report/features/adapter'
import { sourceNote as ragSourceNote, toComparisonView } from '@/routes/report/features/rag-adapter'
import type { ChangeSummary, ComparisonView, PackageVersions } from '@/routes/report/features/model'

/**
 * 기능 분석 실행 상태 (구상안 §9, S15P21A506-217 · BE-130).
 *
 * <h2>무엇을 들고 있나</h2>
 *
 * - 패키지별 **선택한 버전**(드롭다운)과 **완료된 결과의 버전**. 둘이 다르면 `재분석 필요`
 *   이고 PDF 는 막힌다(§9.2, §13.2). 기존 완료 결과는 그대로 유지한다.
 * - 직전 완료 결과. 재분석이 성공하면 클라이언트에서 새 결과와 비교해 변경점을 만든다(§9.5).
 *   서버는 판정을 저장하지 않으므로(`DEC-FEATURE-CACHE-20260917-01`) 새로고침하면 사라진다.
 * - 실패하면 이전 완료 결과를 그대로 둔다. 성공해야만 결과 포인터가 바뀐다(§9.3).
 *
 * <h2>스스로 시작하지 않는다</h2>
 *
 * 예전에는 최신 안정 버전이 다 정해지면 화면에 들어오는 즉시 분석이 돌았다. 지금은 뒤에
 * LLM 생성이 붙고 서버에 동시 실행 상한이 있어(BE-130), 탭을 열기만 한 사람 몫까지 돌리면
 * 정작 누른 사람이 기다린다. **사용자가 누를 때만** `start()` 로 시작한다.
 *
 * <h2>결과를 기다리지 않고 시작한다</h2>
 *
 * 시작은 `run_id` 만 돌려받고(nginx 60초 제한), 그 뒤는 2초 폴링이다(`useFeatureRun`).
 * 단계도 흉내 내지 않는다 — 서버가 `phase` 로 실제 단계를 준다.
 *
 * <h2>소비 조건은 여기 없다</h2>
 *
 * 핵심 비교 요약(`package_env`)은 이 실행과 무관하다. `GET /api/packages/env` 의 키 조회라
 * 버전을 고르는 즉시 뜨고, 분석이 실패해도 그대로 보인다(기능-10-R06).
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
 * - `IDLE`: 아직 시작하지 않음. 사용자가 버튼을 누르기를 기다린다
 * - `RUNNING`: 버전 목록을 받는 중이거나 분석 중. 재분석 중에도 이전 결과가 있으면 그대로 보인다
 * - `COMPLETED`: 완료된 결과가 있고 실행 중이 아님
 * - `FAILED`: 결과가 하나도 없는데 실패함
 * - `UNAVAILABLE`: 이 조합의 기능 비교가 아직 없음
 */
export type RunStatus = 'IDLE' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'UNAVAILABLE'

/**
 * 실패 안내.
 *
 * `VERIFICATION_FAILED` 는 **재시도로 나아지지 않는다** — 파이프라인에 재시도가 없어 다시
 * 눌러도 같은 답이 나온다. 재시도 버튼을 두면 사용자가 헛되이 기다린다.
 */
const ERROR_MESSAGE: Record<FeatureRunErrorCode, string> = {
  DOC_NOT_FOUND: '이 버전의 문헌을 아직 받지 못했습니다.',
  VERIFICATION_FAILED: '판정의 근거를 확인하지 못해 결과를 내지 않았습니다.',
  RAG_UNAVAILABLE: '분석 서버에 연결하지 못했습니다.',
  INTERRUPTED: '분석이 중간에 끊겼습니다.',
}

const RETRYABLE: ReadonlySet<FeatureRunErrorCode> = new Set([
  'DOC_NOT_FOUND',
  'RAG_UNAVAILABLE',
  'INTERRUPTED',
])

export interface AnalysisRun {
  status: RunStatus
  /** 완료된 단계 수. RUN_STEPS 앞에서부터 채워진다. */
  doneCount: number
  /** 시작 후 흐른 초. 서버가 세어 준 값이다 */
  elapsedSec: number
  /** 서버가 말하는 현재 단계. 실행 중이 아니면 null */
  phase: FeatureRunPhase | null
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
  /** 버전까지 정해진 비교 대상. 하나라도 못 고르면 null */
  targets: FeatureTarget[] | null
  /** 지금 화면에 보이는 완료 결과 */
  completed: ComparisonView | null
  /** 완료 결과에 딸린 문헌 상태 안내. 없으면 null */
  sourceNote: string | null
  /** 재분석이 성공한 직후 한 번 보여주는 변경점 */
  changes: ChangeSummary | null
  dismissChanges: () => void
  /** 마지막 시도의 실패. 이전 결과가 있으면 그 결과는 유지된 채로 이것만 알린다 */
  failure: FeatureFailure | null
  /** `선택한 버전으로 분석` 을 누를 수 있는지 */
  canStart: boolean
  retryVersions: () => void
}

interface State {
  /** 이 상태가 어느 비교 대상 조합의 것인지. 조합이 바뀌면 통째로 버린다 */
  key: string
  picks: Record<string, string>
  completed: ComparisonView | null
  sourceNote: string | null
  changes: ChangeSummary | null
  runId: number
  failed: FeatureFailure | null
}

type Action =
  | { type: 'RESET'; key: string }
  | { type: 'PICK'; name: string; version: string }
  | { type: 'START' }
  | { type: 'COMMIT'; view: ComparisonView; note: string | null }
  | { type: 'FAILED'; failure: FeatureFailure }
  | { type: 'DISMISS_CHANGES' }

const initial = (key: string): State => ({
  key,
  picks: {},
  completed: null,
  sourceNote: null,
  changes: null,
  runId: 0,
  failed: null,
})

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'RESET':
      return initial(action.key)
    case 'PICK':
      return { ...state, picks: { ...state.picks, [action.name]: action.version } }
    case 'START':
      // 새 분석을 시작하면 지난 변경점 안내와 실패는 거둔다. 완료 결과는 그대로 둔다.
      return { ...state, runId: state.runId + 1, failed: null, changes: null }
    case 'COMMIT': {
      const diff = state.completed ? diffAnalyses(state.completed, action.view) : null
      return {
        ...state,
        completed: action.view,
        sourceNote: action.note,
        changes: diff && !isEmptyChange(diff) ? diff : null,
        failed: null,
      }
    }
    case 'FAILED':
      // 이전 완료 결과는 건드리지 않는다 — 성공해야만 바뀐다(§9.3)
      return { ...state, failed: action.failure }
    case 'DISMISS_CHANGES':
      return { ...state, changes: null }
  }
}

export function useAnalysisRun(names: readonly string[]): FeatureAnalysis {
  const key = names.join(',')
  const [state, dispatch] = useReducer(reducer, key, initial)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const consumed = useRef<string | null>(null)

  // 비교 대상이 바뀌면 이전 조합의 선택·결과를 통째로 버린다. 렌더 중 dispatch 는 React 가
  // 곧바로 다시 그리므로 낡은 값이 화면에 나가지 않는다.
  if (state.key !== key) dispatch({ type: 'RESET', key })

  const versionsQuery = useFeatureVersions(names)
  const start = useStartFeatureRun()
  const poll = useFeatureRun(activeRunId)

  /**
   * 버전 드롭다운의 선택지 (BE S15P21A506-432).
   *
   * 서버가 **소비 조건이 있는 정식 버전만** 최근 3개 준다. 그래서 어느 것을 골라도 핵심 비교
   * 요약이 채워지고, 사전 배포 버전은 오지 않는다.
   *
   * 패키지는 있는데 고를 버전이 없으면 `latestStable` 이 null 이다 — 자동 선택을 하지 않고,
   * 버전 카드가 "비교할 수 있는 버전이 없다" 로 적는다.
   */
  const versions = useMemo<PackageVersions[] | null>(() => {
    const data = versionsQuery.data
    if (!data) return null
    return data.packages.map((pkg) => ({
      name: pkg.package_name,
      latestStable: pkg.latest_stable,
      choices: pkg.versions.map((version) => ({ version, prerelease: false })),
    }))
  }, [versionsQuery.data])

  /**
   * 고른 이름이 카탈로그에 하나도 없다. 버전을 정할 수 없으니 기능 비교 자체가 없다 —
   * 일부만 없는 경우는 그 패키지의 칸만 비고, 나머지는 그대로 보인다.
   */
  const unavailable = versionsQuery.data !== undefined && versionsQuery.data.packages.length === 0

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

  const running = start.isPending || poll.data?.status === 'RUNNING'

  const restart = useCallback(() => {
    if (!targets || running) return
    dispatch({ type: 'START' })
    setActiveRunId(null)
    start.mutate(targets, {
      onSuccess: (res) => setActiveRunId(res.run_id),
      onError: (error) => {
        const notice = errorNotice(error)
        dispatch({
          type: 'FAILED',
          failure: { message: notice.message, retryable: notice.retryable, kind: 'RUN' },
        })
      },
    })
  }, [targets, running, start])

  /**
   * 폴링 결과를 상태로 옮긴다.
   *
   * 한 run 은 한 번만 반영한다(`consumed`) — 폴링이 멈춘 뒤에도 같은 데이터로 다시 그려질 때
   * 변경점을 또 계산하면 직전 결과와 자기 자신을 비교하게 된다.
   */
  useEffect(() => {
    const data = poll.data
    if (!data || data.status === 'RUNNING' || consumed.current === data.run_id) return
    consumed.current = data.run_id

    if (data.status === 'COMPLETED' && data.result) {
      dispatch({
        type: 'COMMIT',
        view: toComparisonView(data.result),
        note: ragSourceNote(data.result),
      })
      return
    }
    const code = data.error_code
    dispatch({
      type: 'FAILED',
      failure: {
        message: code ? ERROR_MESSAGE[code] : '분석에 실패했습니다.',
        retryable: code ? RETRYABLE.has(code) : true,
        kind: 'RUN',
      },
    })
  }, [poll.data])

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
    : versionsQuery.isLoading || running
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
    failure = state.failed
  }

  return {
    status,
    // 서버가 주는 단계는 셋이라 여섯 칸에 대응하지 않는다. 진행 표시는 `phase` 로 한다.
    doneCount: state.completed && !running ? RUN_STEPS.length : 0,
    elapsedSec: poll.data?.elapsed_sec ?? 0,
    phase: running ? (poll.data?.phase ?? 'PREPARING_DOCS') : null,
    hasCompletedOnce: state.completed !== null,
    runId: state.runId,
    reanalysisRequired,
    restart,
    versions,
    selected,
    select,
    targets,
    completed: state.completed,
    sourceNote: state.sourceNote,
    changes: state.changes,
    dismissChanges,
    failure,
    canStart: targets !== null && !running,
    retryVersions,
  }
}
