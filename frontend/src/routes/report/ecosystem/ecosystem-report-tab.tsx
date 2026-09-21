import { useMemo } from 'react'

import { errorNotice } from '@/api/client'
import { USE_MOCK } from '@/api/endpoints'
import {
  useDependentsTrend,
  useDownloadsTrend,
  usePackagesOverview,
  useRemovalReasons,
  useTransitions,
  useVersionShare,
} from '@/api/queries'
import { MAX_NAMES } from '@/api/types'
import { Skeleton } from '@/components/ui/skeleton'
import { toEcosystemModel } from '@/routes/report/ecosystem/adapter'
import { EcosystemView } from '@/routes/report/ecosystem/ecosystem-view'
import type { MetricKey, MetricState } from '@/routes/report/ecosystem/model'
import { toRemovalReasonsModel } from '@/routes/report/ecosystem/removal-reasons-adapter'
import { toTransitionsModel } from '@/routes/report/ecosystem/transitions-adapter'
import type { TransitionPeriod } from '@/routes/report/ecosystem/transitions-model'

/**
 * 생태계 변화 탭.
 *
 * 명세 §1 이 엔드포인트를 지표별로 나눈 이유가 여기서 그대로 쓰인다 —
 * **네 요청을 각자 기다린다.** 개요가 오면 카드가 먼저 뜨고, 느린 차트 하나 때문에
 * 카드 전체가 붙잡히지 않으며, 버전 분포가 실패해도 나머지는 그려진다.
 *
 * 조회 기간은 더 이상 이 층이 정하지 않는다. 서버가 보유한 전 구간을 주고, 좁히는 일은
 * 화면 안에서 끝난다(S15P21A506-374).
 */
export function EcosystemReportTab({
  packages,
  transitionPeriod,
  onTransitionPeriodChange,
}: {
  packages: string[]
  /**
   * `ReportPage`가 정본으로 들고 있다(S15P21A506-394) — PDF 내보내기가 "화면이 지금 보는
   * 기간"을 그대로 요청에 실어야 해서, 그 값을 쥔 곳이 이 탭 안(언마운트되면 사라지는
   * state)이면 다이얼로그가 못 읽는다. 조회를 쏘는 층과 값을 갖는 층이 갈릴 수 있다는
   * 뜻이라, 아래 `useTransitions` 호출은 여전히 여기서 이 값을 받아서만 한다.
   */
  transitionPeriod: TransitionPeriod
  onTransitionPeriodChange: (next: TransitionPeriod) => void
}) {
  /** 상한을 넘겨 보내면 서버가 V002 로 거절한다. 넘기기 전에 자른다. */
  const names = useMemo(() => [...new Set(packages)].slice(0, MAX_NAMES), [packages])

  const overview = usePackagesOverview(names)

  /**
   * **보유한 전 구간을 한 번에 받는다.** `from`·`to` 를 생략하면 서버가 최초 스냅샷부터
   * 최신 스냅샷까지 준다(S15P21A506-374). 구간을 좁히고 넓히는 일은 전부 화면 안에서
   * 끝나므로, 이 조회는 패키지 조합이 바뀔 때만 다시 나간다.
   *
   * <p>예전에는 상한이 104주라 `from` 을 최신 스냅샷에서 거꾸로 세어 만들었고, 그 날짜를
   * 개요가 알려주기 때문에 **개요가 올 때까지 추이를 보내지 못했다.** 이제 보낼 값이
   * 없으므로 기다릴 이유도 없다 — 세 조회가 동시에 나간다.
   */
  const downloads = useDownloadsTrend(names, undefined, undefined)
  const dependents = useDependentsTrend(names, undefined, undefined)
  /*
    버전 분포만 개요를 기다린다. 카드에 찍는 기준일을 개요와 같은 날짜로 맞춰야 하기
    때문이다. 적재 전에는 snapshot_at 이 null 이라 서버 기본값(최신 스냅샷)에 맡긴다.
  */
  const versionShare = useVersionShare(
    names,
    overview.data?.snapshot_at ?? undefined,
    overview.isSuccess,
  )

  /**
   * 유지·유입·이탈. **개요를 기다리지 않는다** — 기준일이 필요 없고, `period`는
   * 이미 서버가 정한 세 값 중 하나라 다른 조회 결과에 기댈 것이 없다(versionShare가
   * `overview.data?.snapshot_at`을 기다리는 것과 다른 이유).
   *
   * `transitionPeriod` 값 자체는 이제 `ReportPage`가 정본으로 들고 있다(위 프롭 주석,
   * S15P21A506-394) — PDF 내보내기 다이얼로그가 이 탭보다 위에 있어 이 탭 로컬 state로는
   * 못 읽는다. 다만 그 값이 바뀔 때마다 새 요청을 쏘는 자리는 여전히 여기다 — 서버 왕복이
   * 있는 조회라 `ecosystem-view.tsx`의 `window`/`intervalKey`(서버 왕복 없음, 화면 로컬)와
   * 반대 이유로 이 층에 둔다.
   */
  const transitions = useTransitions(names, transitionPeriod)
  /**
   * 이탈 사유 (S15P21A506-410). **같은 `period` 를 쓴다** — 프리셋·기본값·기준일이
   * 같아서 화면이 선택기 하나를 두 패널에 공유한다. 그래도 조회를 나눈 것은 단위가
   * 다르고 엔드포인트가 갈려서다 — 한쪽이 느리거나 실패해도 다른 패널은 그대로 뜬다.
   */
  const removalReasons = useRemovalReasons(names, transitionPeriod)

  if (names.length === 0) {
    return <p className="text-sm text-muted-foreground">비교할 패키지를 먼저 고르세요.</p>
  }

  /**
   * **개요를 아예 못 받았을 때만 화면 전체를 막는다.** 패키지 카드를 만들 재료가 없기 때문이다.
   *
   * 추이 둘은 각자 카드 안에서 실패한다. 예전에는 셋 중 하나만 실패해도 탭 전체가
   * 오류 화면으로 바뀌어, 명세 §1 이 엔드포인트를 지표별로 나눠 둔 이득을 화면이
   * 통째로 버리고 있었다(`DEC-RECONCILIATION-20260910-01` 8번).
   *
   * <p>**갱신 실패는 개요도 화면을 지우지 않는다** — 지표 카드와 같은 판단이다.
   * 이 탭은 비활성일 때 언마운트되므로(Radix `TabsContent`), 다른 탭에 `staleTime`
   * 보다 오래 머물다 돌아오면 네 조회가 전부 다시 나간다. 그때 개요만 한 번 실패해도
   * 멀쩡히 캐시된 보고서가 통째로 오류 화면이 되는 것은 위 원칙과 어긋난다.
   * 재접속(`refetchOnReconnect`) 경로도 같다.
   */
  if (overview.error && !overview.data) {
    return <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />
  }
  if (!overview.data) return <LoadingState />

  const metricState: Record<MetricKey, MetricState> = {
    downloads: stateOf(downloads),
    dependents: stateOf(dependents),
  }
  const versionShareState = stateOf(versionShare)
  const transitionsState = stateOf(transitions)
  const removalReasonsState = stateOf(removalReasons)

  const model = toEcosystemModel({
    overview: overview.data,
    // 아직 안 왔거나 실패한 지표는 넘기지 않는다. 그 카드만 비고 나머지는 그대로 뜬다.
    downloads: downloads.data,
    dependents: dependents.data,
    versionShare: versionShare.data,
  })
  const transitionsModel = toTransitionsModel(transitions.data, names)
  const removalReasonsModel = toRemovalReasonsModel(removalReasons.data, names)

  return (
    <div className="flex flex-col gap-4">
      {/* 개요는 이미 받아 두었는데 갱신만 실패했다. 화면은 두고 사실만 알린다 */}
      {overview.error ? (
        <StaleNotice error={overview.error} onRetry={() => void overview.refetch()} />
      ) : null}
      {USE_MOCK && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
          mock 응답입니다 (<span className="font-mono">VITE_USE_MOCK=true</span>). 값은 지어낸
          것이고, 모양만 v1 API 명세를 따릅니다.
        </p>
      )}
      <EcosystemView
        model={model}
        metricState={metricState}
        versionShareState={versionShareState}
        transitionsModel={transitionsModel}
        transitionsState={transitionsState}
        removalReasonsModel={removalReasonsModel}
        removalReasonsState={removalReasonsState}
        transitionPeriod={transitionPeriod}
        onTransitionPeriodChange={onTransitionPeriodChange}
      />
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
 * 개요를 이미 받아 두었는데 갱신만 실패했다. 지금 보는 것이 최신이 아닐 수 있다는
 * 사실만 알린다 — 지우지도, 조용히 넘기지도 않는다.
 *
 * 지표 카드의 같은 알림과 생김새가 다른 것은 자리가 다르기 때문이다(탭 위 · 카드 안).
 * **판단은 한 벌이다** — 재시도를 권할지는 양쪽 다 `errorNotice` 가 정한다.
 */
function StaleNotice({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const notice = errorNotice(error)

  return (
    <p className="flex flex-wrap items-baseline gap-2 rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
      <span>최신 자료를 받지 못해 마지막으로 받은 것을 그렸습니다.</span>
      {notice.retryable && (
        <button
          type="button"
          onClick={onRetry}
          className="underline underline-offset-2 hover:text-foreground"
        >
          다시 시도
        </button>
      )}
    </p>
  )
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
