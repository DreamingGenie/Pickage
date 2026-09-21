import { errorNotice } from '@/api/client'
import { RemovalBars } from '@/components/charts/removal-bars'
import { seriesStyle } from '@/components/charts/tokens'
import { InfoDialog } from '@/components/common/info-dialog'
import { Skeleton } from '@/components/ui/skeleton'
import type { MetricState } from '@/routes/report/ecosystem/model'
import type { RemovalReasonsModel } from '@/routes/report/ecosystem/removal-reasons-model'
import {
  populationLabel,
  TRANSITION_PERIODS,
  type TransitionPeriod,
} from '@/routes/report/ecosystem/transitions-model'
import { cn } from '@/lib/utils'

/**
 * 이탈 사유 패널 (S15P21A506-410).
 *
 * 바로 위 `TransitionsPanel` 이 **"떠났다" 까지만** 말한다. 이 패널이 그 이탈을 둘로 갈라
 * **왜** 떠났는지를 보여 준다 — 대체 없이 뺐나(필요가 없어졌다), 다른 것과 함께 뺐나.
 *
 * **구간 선택기를 여기 두지 않는다.** 두 패널이 같은 `period` 값을 쓰고 서버가 같은 표에서
 * `t1`·`t2` 를 꺼내므로(`removal_reasons/load.py`), 선택기를 하나 더 두면 같은 값을 바꾸는
 * 컨트롤이 둘이 되어 고장처럼 보인다. 대신 지금 구간을 글로 밝힌다.
 *
 * **단위가 위 패널과 다르다**(전이 건수 vs 패키지 수). 서버가 `unit` 을 값으로 실어 보내는
 * 이유가 이것이라, 그 값을 캡션에 그대로 쓴다 — 문서는 받는 쪽 코드에 닿지 않는다.
 */
export function RemovalReasonsPanel({
  model,
  state,
  period,
  emphasisKeys,
  className,
}: {
  model: RemovalReasonsModel
  state: MetricState
  /** 위 패널과 **같은 값**이다. 이 패널은 바꾸지 않고 보여주기만 한다. */
  period: TransitionPeriod
  emphasisKeys: string[] | null
  className?: string
}) {
  const periodLabel = TRANSITION_PERIODS.find((p) => p.key === period)?.label ?? period
  const dateLabel =
    model.t1 && model.t2
      ? `${model.t1} ~ ${model.t2}`
      : '적재 전 — 아직 이 구간이 계산되지 않았습니다'
  /** 서버가 값으로 보낸 단위. 행이 하나도 없으면 계약상 기본값을 쓴다. */
  const unit = model.packages[0]?.unit ?? 'transitions'

  return (
    <div
      className={cn(
        'flex flex-col gap-5 rounded-2xl border p-6 text-left',
        state.status === 'error' && 'items-start',
        className,
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h3 className="text-lg font-semibold">이탈 사유</h3>
          <InfoDialog label="이탈 사유 계산 기준 안내" title="계산 기준">
            <p>
              위 <strong>유지 · 유입 · 이탈</strong> 과 <strong>세는 단위가 다릅니다.</strong>{' '}
              저쪽은 프로젝트를 이름으로 센 <strong>패키지 수</strong> 이고, 이 수치는 뺀 행위를 센{' '}
              <strong>전이 건수</strong>({unit}) 입니다. 한 프로젝트가 뺐다가 다시 넣고 또 뺐으면
              저쪽은 1, 이쪽은 2 입니다. <strong>두 패널의 수를 더하거나 나누지 마세요.</strong>
            </p>
            <p>
              <strong>다른 것과 함께 제거</strong> 는 같은 릴리스에서 다른 패키지를 함께 넣었다는
              뜻이지, 그것이 <strong>대체품이라는 보장은 아닙니다.</strong> 한 릴리스에 섞인 의존성
              대청소일 수 있습니다.
            </p>
            <p>
              집계 대상은{' '}
              {model.population ? populationLabel(model.population) : '위 패널과 같은 모집단'} 이고,
              구간과 기준일은 위 패널과 같습니다.
            </p>
          </InfoDialog>
        </div>
        <span className="font-mono text-base text-muted-foreground">{dateLabel}</span>
      </div>

      <p className="text-base text-muted-foreground">
        최근 <strong className="text-foreground">{periodLabel}</strong> 간{' '}
        {unit === 'transitions' ? '전이 건수' : unit} 기준입니다. 위 패널과 같은 구간을 봅니다.
      </p>

      {state.status === 'loading' ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      ) : state.status === 'error' ? (
        <PanelError error={state.error} onRetry={state.onRetry} />
      ) : (
        <>
          {model.notFound.length > 0 && (
            <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
              일부 패키지의 이탈 사유를 찾지 못했습니다:{' '}
              <span className="font-mono text-foreground">{model.notFound.join(', ')}</span>
            </p>
          )}

          {/*
            `justify-center` + 고정 폭 — 3패키지면 한 줄을 꽉 채우지만, 1~2개면 그리드가 비운
            칸만큼 오른쪽에 통째로 남던 공백을 양옆으로 고르게 돌린다(리뷰 지적).
          */}
          <div className="flex flex-wrap justify-center gap-5">
            {model.packages.map((pkg, i) => {
              const style = seriesStyle(i)
              const emphasized = !emphasisKeys || emphasisKeys.includes(pkg.key)
              return (
                <div
                  key={pkg.key}
                  className={cn(
                    'flex w-full flex-none flex-col items-center gap-3 transition-opacity duration-150',
                    'sm:basis-[calc(50%-10px)] lg:basis-[calc(33.333%-14px)]',
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
                  <RemovalBars counts={pkg.counts} dataStatus={pkg.dataStatus} />
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function PanelError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
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
