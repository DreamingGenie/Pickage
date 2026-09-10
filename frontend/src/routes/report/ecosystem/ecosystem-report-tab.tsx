import { useMemo } from 'react'

import { ApiError } from '@/api/client'
import { USE_MOCK } from '@/api/endpoints'
import {
  useDependentsTrend,
  useDownloadsTrend,
  usePackagesOverview,
  useVersionShare,
} from '@/api/queries'
import { MAX_NAMES } from '@/api/types'
import { Skeleton } from '@/components/ui/skeleton'
import { toEcosystemModel } from '@/routes/report/ecosystem/adapter'
import { EcosystemView } from '@/routes/report/ecosystem/ecosystem-view'
import { FETCH_WEEKS } from '@/routes/report/ecosystem/model'

/**
 * 생태계 변화 탭.
 *
 * 명세 §1 이 엔드포인트를 지표별로 나눈 이유가 여기서 그대로 쓰인다 —
 * **네 요청을 각자 기다린다.** 개요가 오면 카드가 먼저 뜨고, 느린 차트 하나 때문에
 * 카드 전체가 붙잡히지 않으며, 버전 분포가 실패해도 나머지는 그려진다.
 *
 * 조회 기간만 이 층이 들고 있다. 그것만 `from` 을 바꿔 추이를 다시 받게 하기 때문이고,
 * 개요는 그때 재조회되지 않는다.
 */
export function EcosystemReportTab({ packages }: { packages: string[] }) {
  /** 상한을 넘겨 보내면 서버가 V002 로 거절한다. 넘기기 전에 자른다. */
  const names = useMemo(() => [...new Set(packages)].slice(0, MAX_NAMES), [packages])

  /**
   * **상한만큼 한 번에 받는다.** 구간을 좁히고 넓히는 일은 전부 화면 안에서 끝나므로
   * 이 조회는 패키지 조합이 바뀔 때만 다시 나간다.
   *
   * <p>`from` 은 오늘이 아니라 **최신 스냅샷**을 기준으로 세어야 하는데, 그 날짜는 개요
   * 응답이 알려준다. 개요가 오기 전에는 `from` 을 비워 서버 기본값에 맡긴다 — 명세 §4 가
   * 그 경우를 정의해 두었으므로 클라이언트가 날짜를 지어낼 이유가 없다. 개요가 도착하면
   * 104주로 다시 한 번 나가는데, 그 뒤로는 조작을 아무리 해도 더 나가지 않는다.
   */
  const overview = usePackagesOverview(names)
  const from = useMemo(() => {
    const latest = overview.data?.snapshot_at
    if (!latest) return undefined
    return new Date(Date.parse(latest) - (FETCH_WEEKS - 1) * 7 * 864e5).toISOString().slice(0, 10)
  }, [overview.data?.snapshot_at])

  const downloads = useDownloadsTrend(names, from)
  const dependents = useDependentsTrend(names, from)
  // 적재 전에는 snapshot_at 이 null 이다. 서버 기본값(최신 스냅샷)에 맡긴다.
  const versionShare = useVersionShare(names, overview.data?.snapshot_at ?? undefined)

  if (names.length === 0) {
    return <p className="text-sm text-muted-foreground">비교할 패키지를 먼저 고르세요.</p>
  }

  const error = overview.error ?? downloads.error ?? dependents.error
  if (error) return <ErrorState error={error} onRetry={() => void overview.refetch()} />

  if (!overview.data || !downloads.data || !dependents.data) {
    return <LoadingState />
  }

  const model = toEcosystemModel({
    overview: overview.data,
    downloads: downloads.data,
    dependents: dependents.data,
    // 실패하면 카드의 Version Share 자리만 비고 나머지는 그대로 뜬다.
    versionShare: versionShare.data,
  })

  return (
    <div className="flex flex-col gap-4">
      {USE_MOCK && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-[11.5px] text-muted-foreground">
          mock 응답입니다 (<span className="font-mono">VITE_USE_MOCK=true</span>). 값은 지어낸
          것이고, 모양만 v1 API 명세를 따릅니다.
        </p>
      )}
      <EcosystemView model={model} />
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex flex-col gap-5">
      <Skeleton className="h-8 w-full max-w-md" />
      <Skeleton className="h-[268px] w-full" />
      <Skeleton className="h-[268px] w-full" />
    </div>
  )
}

/**
 * 400 계열은 사용자가 고칠 수 있는 것이라(이름 형식·개수) 서버 문구를 그대로 보여준다.
 * 그 밖의 오류만 재시도를 권한다 — 같은 요청을 다시 보내도 결과가 같기 때문이다.
 */
function ErrorState({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const api = error instanceof ApiError ? error : null
  const retryable = !api?.isValidation

  return (
    <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed p-6">
      <p className="text-sm">{api?.message ?? '자료를 불러오지 못했습니다.'}</p>
      {api && <p className="font-mono text-[11px] text-muted-foreground">{api.code}</p>}
      {retryable && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border px-3 py-1.5 text-xs transition-colors hover:border-foreground/40"
        >
          다시 시도
        </button>
      )}
    </div>
  )
}
