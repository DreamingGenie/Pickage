import { useEffect, useRef, useState } from 'react'

/**
 * 기능 분석 진행 상태 (구상안 9.4).
 *
 * 완료되지 않은 단계를 완료로 보내지 않는다. 서버가 실제로 그 단계를 끝냈다고
 * 알려줄 때만 체크가 올라간다.
 *
 * 미해결: 지금은 시간에 따라 단계를 흉내 낸다.
 * 실제로는 SSE(또는 동등한 단방향 스트림)로 받아야 하고, 재연결 시
 * 현재 run 상태를 조회할 수 있어야 한다.
 */
export const RUN_STEPS = [
  { key: 'VERSION_VERIFIED', label: '정확한 버전 확인' },
  { key: 'ARTIFACT_COLLECTED', label: '배포본 수집 · 무결성 검증' },
  { key: 'ENVIRONMENT_EXTRACTED', label: '환경 · 설치 조건 추출' },
  { key: 'EVIDENCE_EXTRACTED', label: '근거 추출' },
  { key: 'ASSESSMENTS_LINKED', label: '판정 연결' },
  { key: 'NARRATIVE_GENERATED', label: '중립 해설 생성' },
] as const

export type RunStatus = 'RUNNING' | 'COMPLETED' | 'FAILED'

export interface AnalysisRun {
  status: RunStatus
  /** 완료된 단계 수. RUN_STEPS 앞에서부터 채워진다. */
  doneCount: number
  /** 시작 후 흐른 초 */
  elapsedSec: number
  /** 한 번이라도 완료된 적이 있는지. 재분석 중에도 이전 결과를 계속 보여주려면 필요하다. */
  hasCompletedOnce: boolean
  /** 새 run 시작. 성공해야만 결과 포인터가 바뀐다(구상안 9.3). */
  restart: () => void
}

/** 단계별 소요 시간 흉내. 근거 추출이 제일 오래 걸린다. */
const STEP_MS = [700, 1500, 900, 3200, 1100, 1800]

export function useAnalysisRun(): AnalysisRun {
  const [runId, setRunId] = useState(0)
  const [doneCount, setDone] = useState(0)
  const [elapsedSec, setElapsed] = useState(0)
  const [hasCompletedOnce, setCompletedOnce] = useState(false)
  const startedAt = useRef<number | null>(null)

  useEffect(() => {
    startedAt.current = Date.now()
    setDone(0)
    setElapsed(0)

    const timers: number[] = []
    let acc = 0
    STEP_MS.forEach((ms, i) => {
      acc += ms
      timers.push(
        window.setTimeout(() => {
          setDone(i + 1)
          if (i + 1 === STEP_MS.length) setCompletedOnce(true)
        }, acc),
      )
    })

    const tick = window.setInterval(() => {
      if (startedAt.current) setElapsed(Math.floor((Date.now() - startedAt.current) / 1000))
    }, 1000)

    return () => {
      timers.forEach(clearTimeout)
      clearInterval(tick)
    }
  }, [runId])

  return {
    status: doneCount >= RUN_STEPS.length ? 'COMPLETED' : 'RUNNING',
    doneCount,
    elapsedSec,
    hasCompletedOnce,
    restart: () => setRunId((n) => n + 1),
  }
}
