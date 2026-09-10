import { useMemo } from 'react'

import { errorNotice } from '@/api/client'
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
import { FETCH_WEEKS, type MetricKey, type MetricState } from '@/routes/report/ecosystem/model'

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
   * 응답이 알려준다. 그래서 **개요가 올 때까지 추이를 아예 보내지 않는다.**
   *
   * <p>예전에는 개요를 기다리지 않고 `from` 없이 먼저 한 번 보내 서버 기본값(26주)에
   * 맡겼다. "카드가 먼저 뜨게 하려고" 였는데 <b>실제로는 그런 적이 없다</b> — 아래 렌더
   * 게이트가 개요·다운로드·의존 세 응답을 모두 기다리므로, 먼저 온 26주 응답은 화면에
   * 뜨지 못한 채 개요 도착과 함께 질의 키가 바뀌며 버려졌다. 2026-09-10 실측에서 보고서
   * 한 번 여는 데 추이 3종이 두 번씩, 즉 요청 7개가 나갔다(필요한 것은 4개).
   */
  const overview = usePackagesOverview(names)
  const from = useMemo(() => {
    const latest = overview.data?.snapshot_at
    if (!latest) return undefined
    return new Date(Date.parse(latest) - (FETCH_WEEKS - 1) * 7 * 864e5).toISOString().slice(0, 10)
  }, [overview.data?.snapshot_at])

  /**
   * 적재 전에는 개요가 성공해도 `snapshot_at` 이 null 이라 `from` 이 계속 비어 있다.
   * 그래서 `from` 이 아니라 **개요가 왔는지**로 문을 연다 — 그러지 않으면 자료가 없을 때
   * 추이가 영원히 안 나가고 화면이 로딩에서 멈춘다.
   */
  const ready = overview.isSuccess

  const downloads = useDownloadsTrend(names, from, undefined, ready)
  const dependents = useDependentsTrend(names, from, undefined, ready)
  // 적재 전에는 snapshot_at 이 null 이다. 서버 기본값(최신 스냅샷)에 맡긴다.
  const versionShare = useVersionShare(names, overview.data?.snapshot_at ?? undefined, ready)

  if (names.length === 0) {
    return <p className="text-sm text-muted-foreground">비교할 패키지를 먼저 고르세요.</p>
  }

  /**
   * **개요 실패만 화면 전체를 막는다.** 패키지 카드를 만들 재료가 없기 때문이다.
   *
   * 추이 둘은 각자 카드 안에서 실패한다. 예전에는 셋 중 하나만 실패해도 탭 전체가
   * 오류 화면으로 바뀌어, 명세 §1 이 엔드포인트를 지표별로 나눠 둔 이득을 화면이
   * 통째로 버리고 있었다(`DEC-RECONCILIATION-20260910-01` 8번).
   */
  if (overview.error) {
    return <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />
  }
  if (!overview.data) return <LoadingState />

  const metricState: Record<MetricKey, MetricState> = {
    downloads: stateOf(downloads),
    dependents: stateOf(dependents),
  }

  const model = toEcosystemModel({
    overview: overview.data,
    // 아직 안 왔거나 실패한 지표는 넘기지 않는다. 그 카드만 비고 나머지는 그대로 뜬다.
    downloads: downloads.data,
    dependents: dependents.data,
    versionShare: versionShare.data,
  })

  return (
    <div className="flex flex-col gap-4">
      {USE_MOCK && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
          mock 응답입니다 (<span className="font-mono">VITE_USE_MOCK=true</span>). 값은 지어낸
          것이고, 모양만 v1 API 명세를 따릅니다.
        </p>
      )}
      <EcosystemView model={model} metricState={metricState} />
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
 * 추이 한 개의 처지를 카드가 알아들을 모양으로 옮긴다.
 *
 * `isPending` 이 아니라 데이터 유무로 판정한다 — 개요가 오기 전에는 `ready` 가 아니라
 * 아예 꺼져 있고(`enabled: false`), 그때 react-query 의 상태는 `pending` 이지만
 * 가져오는 중은 아니다. 화면에는 둘 다 "기다리는 중" 으로 보이는 게 맞다.
 */
function stateOf(q: { data: unknown; error: unknown; refetch: () => unknown }): MetricState {
  const onRetry = () => void q.refetch()
  // 받아 둔 자료가 있으면 그것을 먼저 친다. 갱신 실패로 이미 그린 차트를 지우지 않는다.
  if (q.data) return { status: 'ready', refreshError: q.error ?? undefined, onRetry }
  if (q.error) return { status: 'error', error: q.error, onRetry }
  return { status: 'loading' }
}

/**
 * 400 계열은 사용자가 고칠 수 있는 것이라(이름 형식·개수) 서버 문구를 그대로 보여준다.
 * 그 밖의 오류만 재시도를 권한다 — 같은 요청을 다시 보내도 결과가 같기 때문이다.
 */
function ErrorState({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const notice = errorNotice(error)

  return (
    <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed p-6">
      <p className="text-sm">{notice.message}</p>
      {notice.code && <p className="font-mono text-base text-muted-foreground">{notice.code}</p>}
      {notice.retryable && (
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
