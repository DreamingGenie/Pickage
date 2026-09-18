import { InfoIcon } from 'lucide-react'
import { useMemo, useState } from 'react'

import { errorNotice } from '@/api/client'
import { TransitionBars } from '@/components/charts/transition-bars'
import { seriesStyle } from '@/components/charts/tokens'
import { SegmentedControl } from '@/components/common/segmented-control'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import type { MetricState } from '@/routes/report/ecosystem/model'
import {
  TRANSITION_KIND_INFO,
  TRANSITION_KINDS,
  TRANSITION_PERIODS,
  type TransitionKind,
  type TransitionPeriod,
  type TransitionsModel,
} from '@/routes/report/ecosystem/transitions-model'
import { cn } from '@/lib/utils'

/**
 * 유지·유입·이탈 패널 (S15P21A506-391).
 *
 * 그리드(Dependents·Downloads·PackageCard) 아래 **전체 폭 섹션**으로 둔다 — 좌측
 * sticky 칼럼은 "칩 강조가 두 차트에 동시에 걸리는" 용도인데 이 패널은 자체 날짜축을
 * 가진 구조적으로 독립된 데이터라 그 관계에 안 낀다. 3패키지×4범주를 좁은 칼럼에
 * 욱여넣지 않기 위한 선택이기도 하다.
 *
 * 기간(`period`)은 **부모가 들고 있다** — `ecosystem-view.tsx`의 `window`/`intervalKey`와
 * 같은 이유(39행)의 반대쪽이다: 그건 서버 왕복이 없어 로컬에 두지만, 이건 프리셋을
 * 바꿀 때마다 새 요청이 나가므로 그 요청을 쏘는 층(`EcosystemReportTab`)이 정본이어야
 * 한다. `kind`는 서버 왕복이 없는 순수 재배치라 이 컴포넌트 로컬 상태로 둔다.
 */
export function TransitionsPanel({
  model,
  state,
  period,
  onPeriodChange,
  emphasisKeys,
  className,
}: {
  model: TransitionsModel
  state: MetricState
  period: TransitionPeriod
  onPeriodChange: (next: TransitionPeriod) => void
  /** 위 칩 줄이 고른 패키지 — 다른 차트·카드와 같은 강조를 이 패널에도 건다. */
  emphasisKeys: string[] | null
  className?: string
}) {
  const [kind, setKind] = useState<TransitionKind>('regular')

  const rowsOf = (pkg: TransitionsModel['packages'][number]) =>
    pkg.rows.find((r) => r.kind === kind) ?? null

  /**
   * 비교 패키지 전체에서 공유하는 스케일. 개별 컴포넌트가 각자 최댓값을 잡으면
   * 패키지끼리 막대 길이로 비교할 수 없다 — Dependents·Downloads 차트가 이미 비교
   * 패키지 간 공유 축을 쓰는 것과 같은 이유다. `OUT_OF_SCOPE`·`NOT_COMPUTED`는
   * 고정 placeholder 폭이라 스케일 계산에서 뺀다.
   */
  const max = useMemo(() => {
    let m = 0
    for (const pkg of model.packages) {
      const row = rowsOf(pkg)
      if (!row?.counts) continue
      m = Math.max(
        m,
        row.counts.retained,
        row.counts.inflowAdopted,
        row.counts.outflow,
        row.counts.unobserved,
      )
    }
    return m
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model.packages, kind])

  const dateLabel =
    model.t1 && model.t2
      ? `${model.t1} ~ ${model.t2}`
      : '적재 전 — 아직 이 구간이 계산되지 않았습니다'

  return (
    <div
      className={cn(
        'flex flex-col gap-5 rounded-2xl border p-6 text-left',
        state.status === 'error' && 'items-start',
        className,
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-lg font-semibold">유지 · 유입 · 이탈</h3>
        <span className="font-mono text-base text-muted-foreground">{dateLabel}</span>
      </div>

      <p className="text-base leading-relaxed text-muted-foreground">
        Dependents 그래프의 증감과는 다른 기준입니다 — 모집단·계산 방식이 다릅니다.
      </p>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl
          label="조회 기간"
          value={period}
          onChange={(k) => onPeriodChange(k as TransitionPeriod)}
          options={TRANSITION_PERIODS.map((p) => ({ key: p.key, label: p.label }))}
        />
        <div className="flex items-center gap-1.5">
          <SegmentedControl
            label="의존 종류"
            value={kind}
            onChange={(k) => setKind(k as TransitionKind)}
            options={TRANSITION_KINDS.map((k) => ({ key: k.key, label: k.label }))}
          />
          <Dialog>
            <DialogTrigger asChild>
              <button
                type="button"
                aria-label="의존 종류 안내"
                className="rounded-full p-0.5 text-muted-foreground/70 transition-colors hover:text-foreground"
              >
                <InfoIcon aria-hidden className="size-3.5" />
              </button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-sm">
              <DialogHeader>
                <DialogTitle>의존 종류</DialogTitle>
              </DialogHeader>
              <dl className="flex flex-col gap-3">
                {TRANSITION_KIND_INFO.map((info) => (
                  <div key={info.key}>
                    <dt className="text-base font-medium">{info.label}</dt>
                    <dd className="text-base leading-relaxed text-muted-foreground">
                      {info.description}
                    </dd>
                  </div>
                ))}
              </dl>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {state.status === 'loading' ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      ) : state.status === 'error' ? (
        <TransitionsError error={state.error} onRetry={state.onRetry} />
      ) : (
        <>
          {model.notFound.length > 0 && (
            <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
              일부 패키지의 전환 데이터를 찾지 못했습니다:{' '}
              <span className="font-mono text-foreground">{model.notFound.join(', ')}</span>
            </p>
          )}

          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {model.packages.map((pkg, i) => {
              const row = rowsOf(pkg)
              const style = seriesStyle(i)
              const emphasized = !emphasisKeys || emphasisKeys.includes(pkg.key)
              return (
                <div
                  key={pkg.key}
                  className={cn(
                    'flex flex-col gap-3 transition-opacity duration-150',
                    !emphasized && 'opacity-40',
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    <svg width="16" height="8" aria-hidden className="shrink-0">
                      <line
                        x1="0"
                        y1="4"
                        x2="16"
                        y2="4"
                        stroke={style.color}
                        strokeWidth="2.4"
                        strokeDasharray={style.dash}
                        strokeLinecap="round"
                      />
                    </svg>
                    <span className="truncate font-mono text-base font-medium">{pkg.key}</span>
                  </div>
                  {row ? (
                    <TransitionBars counts={row.counts} dataStatus={row.dataStatus} max={max} />
                  ) : (
                    <p className="text-base text-muted-foreground">자료 없음</p>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}

      <p className="text-base text-muted-foreground/80">devDependencies는 포함하지 않습니다.</p>
    </div>
  )
}

function TransitionsError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const notice = errorNotice(error)
  return (
    <div className="flex flex-col items-start gap-2 rounded-xl border border-dashed px-4 py-3 text-base text-muted-foreground">
      <span className="font-medium text-foreground">{notice.message}</span>
      {onRetry && notice.retryable && (
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
