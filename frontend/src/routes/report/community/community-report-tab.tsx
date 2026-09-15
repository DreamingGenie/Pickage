import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { errorNotice } from '@/api/client'
import { USE_MOCK } from '@/api/endpoints'
import { useCommunityRefresh, useCommunityStatus } from '@/api/queries'
import { queryKeys } from '@/api/queries/keys'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { noticeFromRefresh, toProgressModel } from '@/routes/report/community/adapter'
import type { CommunityNotice } from '@/routes/report/community/model'
import { CommunityProgress } from '@/routes/report/community/progress'
import { CommunityResultView } from '@/routes/report/community/result'

function useDocumentVisible(): boolean {
  const [visible, setVisible] = useState(() => document.visibilityState === 'visible')
  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState === 'visible')
    document.addEventListener('visibilitychange', onChange)
    return () => document.removeEventListener('visibilitychange', onChange)
  }, [])
  return visible
}

/**
 * GitHub 커뮤니티 현황 탭(S15P21A506-316).
 *
 * `report-page.tsx`가 이 탭을 마운트 보존하므로(생태계 필터 유지 목적) 언마운트로
 * 폴링을 멈출 수 없다 — `active`(현재 선택된 탭인가)와 문서 가시성을 함께 봐서
 * 명시적으로 폴링을 끈다.
 */
export function CommunityReportTab({
  basePackage,
  baseConflict,
  active,
}: {
  basePackage: string | null
  baseConflict: boolean
  active: boolean
}) {
  const name = basePackage ?? ''
  const documentVisible = useDocumentVisible()
  const hasContext = Boolean(basePackage) && !baseConflict
  const enabled = active && documentVisible && hasContext

  const status = useCommunityStatus(name, enabled)
  const refresh = useCommunityRefresh()
  const queryClient = useQueryClient()

  /**
   * admission 거절 notice(§8.2). GET registry 에 안 남는 순간의 안내라 화면이 기억한다.
   * 새 active task 확인이나 RESULT 도착 시에만 해제한다 — 뒤이은 IDLE 이 지우지 않는다.
   */
  const [notice, setNotice] = useState<CommunityNotice | null>(null)
  useEffect(() => {
    if (status.data?.refresh?.refresh_id || status.data?.view_status === 'RESULT') {
      setNotice(null)
    }
  }, [status.data])

  function sendRefresh(trigger: 'TAB_OPENED') {
    if (!basePackage) return
    refresh.mutate(
      { name: basePackage, trigger },
      {
        onSuccess: (data) => {
          queryClient.setQueryData(queryKeys.community.status(basePackage), data)
          setNotice(noticeFromRefresh(data.refresh))
        },
        // POST 실패는 여기서 흡수한다 — GET 폴링은 이미 돌고 있으므로 화면을 막지 않는다.
        onError: () => {},
      },
    )
  }

  /**
   * 최초 GET 결과를 보고 필요할 때만 `TAB_OPENED` POST 를 한 번 보낸다(§8.2).
   * `postedForRef` 로 basePackage 당 한 번만 — StrictMode 이중 effect·매 폴링마다
   * 재실행되는 것을 막는다.
   */
  const postedForRef = useRef<string | null>(null)
  useEffect(() => {
    if (!basePackage || baseConflict || !status.isSuccess) return
    if (postedForRef.current === basePackage) return
    postedForRef.current = basePackage

    const data = status.data
    const summaryRetryDue =
      data.result?.summary_status === 'FAILED' &&
      (!data.result.summary_retry_at || Date.parse(data.result.summary_retry_at) <= Date.now())
    const needsRefresh =
      data.view_status === 'IDLE' ||
      (data.view_status === 'RESULT' && (data.freshness === 'STALE' || summaryRetryDue))

    if (needsRefresh) sendRefresh('TAB_OPENED')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basePackage, baseConflict, status.isSuccess, status.data])

  /** fresh/serve 경계에 정확히 맞춰 한 번만 재조회한다(결정 5) — 막연한 폴링이 아니다. */
  useEffect(() => {
    if (!active) return
    const result = status.data?.result
    const refreshStatus = status.data?.refresh?.status
    if (!result || refreshStatus === 'QUEUED' || refreshStatus === 'RUNNING') return

    const timers = [Date.parse(result.fresh_until), Date.parse(result.serve_until)]
      .map((at) => at - Date.now())
      .filter((ms) => ms > 0)
      .map((ms) => window.setTimeout(() => void status.refetch(), ms + 50))
    return () => timers.forEach(clearTimeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    active,
    status.data?.result?.fresh_until,
    status.data?.result?.serve_until,
    status.data?.refresh?.status,
  ])

  /**
   * "다시 시도" 버튼의 비활성 여부. **렌더 중 `Date.now()`를 직접 비교하지 않는다** —
   * 렌더는 순수해야 하므로(react-hooks/purity), 판정은 effect 안에서 하고 그 시각에
   * 맞춰 스스로 풀리는 타이머를 건다.
   */
  const [retryDisabled, setRetryDisabled] = useState(false)
  useEffect(() => {
    if (!notice?.retryAt) {
      setRetryDisabled(false)
      return
    }
    const ms = Date.parse(notice.retryAt) - Date.now()
    if (ms <= 0) {
      setRetryDisabled(false)
      return
    }
    setRetryDisabled(true)
    const id = window.setTimeout(() => setRetryDisabled(false), ms + 50)
    return () => clearTimeout(id)
  }, [notice?.retryAt])

  if (!basePackage && !baseConflict) {
    return (
      <GuidanceCard message="비교 대상을 다시 확인해 주세요. 기준 패키지 정보가 없어 커뮤니티 현황을 조회할 수 없습니다." />
    )
  }
  if (baseConflict) {
    return (
      <GuidanceCard message="기준 패키지 정보가 일치하지 않습니다. 분석을 새로 시작해 주세요." />
    )
  }

  if (status.isPending) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  if (status.isError) {
    const n = errorNotice(status.error)
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed p-6">
        <p className="text-sm">{n.message}</p>
        {n.retryable && (
          <Button size="sm" variant="outline" onClick={() => void status.refetch()}>
            다시 시도
          </Button>
        )}
      </div>
    )
  }

  const data = status.data

  return (
    <div className="flex flex-col gap-4">
      {USE_MOCK && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
          mock 응답입니다 (<span className="font-mono">VITE_USE_MOCK=true</span>). 값은 지어낸
          것이고, 모양만 API 계약을 따릅니다.
        </p>
      )}

      {notice && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed px-3 py-2">
          <p className="text-sm">{notice.message}</p>
          <Button
            size="sm"
            variant="outline"
            disabled={retryDisabled}
            onClick={() => sendRefresh('TAB_OPENED')}
          >
            다시 시도
          </Button>
        </div>
      )}

      {data.view_status === 'PROCESSING' && data.refresh && (
        <>
          {data.result && data.freshness && (
            <CommunityResultView result={data.result} freshness={data.freshness} />
          )}
          <CommunityProgress progress={toProgressModel(data.refresh)} />
        </>
      )}

      {data.view_status === 'RESULT' && data.result && data.freshness && (
        <CommunityResultView result={data.result} freshness={data.freshness} />
      )}

      {data.view_status === 'IDLE' && !notice && (
        <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed p-6">
          <p className="text-sm">아직 커뮤니티 현황을 수집하지 않았습니다.</p>
          <Button size="sm" onClick={() => sendRefresh('TAB_OPENED')}>
            수집 시작
          </Button>
        </div>
      )}
    </div>
  )
}

function GuidanceCard({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed p-6">
      <p className="text-sm">{message}</p>
    </div>
  )
}
