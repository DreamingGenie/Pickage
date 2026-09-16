import { useEffect, useRef, useState } from 'react'

import type { CommunityProgressModel } from '@/routes/report/community/model'

function useElapsedSeconds(startedAt: string | null): number {
  const [elapsed, setElapsed] = useState(0)
  const startedRef = useRef(startedAt)

  useEffect(() => {
    startedRef.current = startedAt
    if (!startedAt) {
      setElapsed(0)
      return
    }
    const startMs = Date.parse(startedAt)
    setElapsed(Math.max(0, Math.floor((Date.now() - startMs) / 1000)))
    const id = window.setInterval(() => {
      setElapsed(Math.max(0, Math.floor((Date.now() - startMs) / 1000)))
    }, 1000)
    return () => clearInterval(id)
  }, [startedAt])

  return elapsed
}

/**
 * 진행 중 카드. **서버가 준 `stageMessage`만 그대로 보여준다** — 가짜 퍼센트·가짜 단계
 * 목록을 만들지 않는다(구현계획 §8.3). `startedAt`이 아직 없으면(QUEUED) 경과시간
 * 대신 대기 문구만 보인다.
 */
export function CommunityProgress({ progress }: { progress: CommunityProgressModel }) {
  const elapsed = useElapsedSeconds(progress.startedAt)

  return (
    <div
      className="flex flex-col gap-2 rounded-xl border border-dashed p-4"
      role="status"
      aria-live="polite"
    >
      <p className="text-sm">{progress.stageMessage}</p>
      {progress.startedAt && (
        <p className="font-mono text-base text-muted-foreground">경과 {elapsed}초</p>
      )}
    </div>
  )
}
