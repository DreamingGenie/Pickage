import type { ChartSeries } from '@/components/charts/geometry'
import { LineChart, SeriesLegend } from '@/components/charts/line-chart'
import { errorNotice } from '@/api/client'
import { Skeleton } from '@/components/ui/skeleton'
import {
  MIN_POINTS_FOR_LINE,
  type MetricState,
  type SnapshotWindow,
} from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

/** 결측을 뺀, 실제로 그릴 수 있는 관측치 수. */
function validCount(s: ChartSeries): number {
  return s.points.filter((p) => p.v !== null).length
}

/**
 * 지표 하나짜리 독립 카드.
 *
 * 기간·간격은 위 조작줄에서 받아 쓰되, **자를지 말지는 각자 판단한다.**
 * 시리즈마다 관측 시작이 달라(명세 §4) 고른 구간이 이 지표의 시작보다 앞서면
 * 여기서 잘리고, 잘렸다는 사실을 카드 안에서 알린다.
 *
 * 점이 너무 적으면 선을 그리지 않는다. 스냅샷 두 개를 이은 직선은 추세처럼 보이지만
 * 추세가 아니다 — 서비스 초기에는 이 상태가 몇 주 이어진다(명세 §4 화면 연결).
 */
export function MetricChart({
  title,
  unit,
  series,
  step,
  window,
  observedFrom,
  coverageNote,
  maxWeeksNote,
  emphasisKeys = null,
  height = 192,
  showLegend = false,
  state = { status: 'ready' },
  className,
}: {
  title: string
  unit: string
  /** 이미 표시 구간·간격이 반영된 시리즈다 — 여기서 다시 자르지 않는다(부르는 쪽: `EcosystemView`). */
  series: ChartSeries[]
  /** 공백 판정(`maxGapDays`)과 푸터의 "N주 간격" 표시에 쓴다. */
  step: number
  window: SnapshotWindow
  observedFrom?: string
  coverageNote?: string
  /** Downloads 카드의 "최대 104주 조회" 같은 고정 안내(126). 카드마다 다르면 부르는 쪽이 정한다. */
  maxWeeksNote?: string
  emphasisKeys?: readonly string[] | null
  height?: number
  showLegend?: boolean
  /** 이 카드만의 처지. 옆 카드와 섞이지 않는다. */
  state?: MetricState
  className?: string
}) {
  /** 고른 시작이 이 지표의 관측 시작보다 앞서면 여기서 잘린다. */
  const clamped = Boolean(observedFrom && window.start < observedFrom)

  /**
   * **시리즈별로** 선을 그릴지 가른다(311b) — 예전에는 가장 긴 시리즈 하나로 카드 전체를
   * gate 해서, 짧은 시리즈 하나가 다른 시리즈들 옆에 추세인 것처럼 그대로 그려졌다.
   * "관측 행이 있는가"(raw)와 "그릴 값이 있는가"(valid, null 제외)도 구분한다.
   */
  const rawMax = Math.max(0, ...series.map((s) => s.points.length))
  const allDates = [...new Set(series.flatMap((s) => s.points.map((p) => p.t)))].sort()
  const maxValidPoints = Math.max(0, ...series.map(validCount))

  const lined = series.filter((s) => validCount(s) >= MIN_POINTS_FOR_LINE)
  const accumulating = series.filter((s) => {
    const c = validCount(s)
    return c > 0 && c < MIN_POINTS_FOR_LINE
  })

  return (
    <section className={cn('flex min-w-0 flex-col gap-4 rounded-2xl border p-6', className)}>
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="font-mono text-base text-muted-foreground">{unit}</span>
      </header>

      {showLegend && state.status === 'ready' && (
        <SeriesLegend series={series} emphasisKeys={emphasisKeys} />
      )}

      {state.status === 'loading' ? (
        <Skeleton className="w-full rounded-xl" style={{ height }} />
      ) : state.status === 'error' ? (
        <MetricError height={height} error={state.error} onRetry={state.onRetry} />
      ) : rawMax === 0 ? (
        <EmptyState height={height}>이 구간에 관측된 스냅샷이 없습니다.</EmptyState>
      ) : lined.length === 0 ? (
        /*
          점 두 개를 선으로 이으면 없는 추세를 그린 것이 된다. 시리즈 전부가 이 상태라
          그릴 선이 하나도 없다 — 관측치는 숨기지 않고 그대로 적되, 선은 그리지 않는다.
        */
        <EmptyState height={height}>
          {accumulating.map((s) => (
            <span key={s.key}>
              <span className="font-medium text-foreground">{s.label}</span> 데이터 축적 중 ·{' '}
              {validCount(s)}주차
            </span>
          ))}
          <span>추세를 그리려면 스냅샷이 {MIN_POINTS_FOR_LINE}개 이상 필요합니다.</span>
        </EmptyState>
      ) : (
        <>
          <LineChart
            series={lined}
            height={height}
            emphasisKeys={emphasisKeys}
            observedFrom={observedFrom}
            /*
              공백 판정 기준을 지금 보고 있는 간격에 맞춘다.

              매주 보기(step 1)면 8일이지만, 4주 간격으로 솎아 보는 중이면 이웃 점 사이가
              원래 28일이다. 8일을 그대로 쓰면 정상 구간까지 전부 공백으로 판정돼 선이
              아예 사라진다.

              **솎아도 공백은 그대로 드러난다.** `sampleEvery` 가 시간이 아니라 인덱스로
              솎으므로 남은 두 점은 항상 정확히 step 칸 떨어져 있고, 그 사이에 행이 하나라도
              빠지면 간격이 (step+1)×7 일이 되어 이 기준을 반드시 넘는다. 그래서 이 식은
              배율이 무엇이든 **"사이에 빠진 주가 있는가"** 라는 같은 질문을 던진다.

              비례해서 느슨하게 잡으면 안 된다. step×7 의 1.5 배쯤으로 두면 분기 보기의
              임계값이 19주가 되어 **한 달 넘는 수집 중단이 연속한 선으로 그려진다** —
              이 판정을 넣은 이유(`DEC-RECONCILIATION-20260910-01` 7번)를 가장 티가 안 나는
              자리에서 다시 어기는 셈이다.

              +1 일은 수집 시각이 밀리는 데 대한 여유다. 한 주(7일)보다 작기만 하면 위 등가성이
              유지되므로, 여유가 모자라면 배율과 무관하게 이 값만 키우면 된다.
            */
            maxGapDays={step * 7 + 1}
            ariaLabel={`${title} 추이`}
          />
          {/* 선을 그리기엔 짧은 시리즈가 옆에 남아 있으면 숨기지 않고 따로 알린다(311b) */}
          {accumulating.length > 0 && <AccumulatingNotes series={accumulating} />}
        </>
      )}

      {/* 구간·개수는 받은 자료를 설명하는 줄이다. 못 받았으면 할 말이 없다 */}
      {state.status === 'ready' && (
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-t pt-3 text-base text-muted-foreground">
          <span className="font-mono">
            {allDates.length ? `${allDates[0]} ~ ${allDates[allDates.length - 1]}` : '자료 없음'}
          </span>
          <span className="font-mono tabular-nums">
            스냅샷 {maxValidPoints}개{step > 1 && ` · ${step}주 간격`}
          </span>
        </div>
      )}

      {state.status === 'ready' && state.refreshError !== undefined && (
        <RefreshNotice error={state.refreshError} onRetry={state.onRetry} />
      )}

      {state.status === 'ready' && clamped && (
        <p className="-mt-1.5 text-base leading-relaxed text-muted-foreground">
          {coverageNote ?? '수집된 구간을 넘습니다'} — 이 지표는 {observedFrom} 부터 있어 그 뒤만
          그렸습니다.
        </p>
      )}

      {state.status === 'ready' && maxWeeksNote && (
        <p className="-mt-1.5 text-base leading-relaxed text-muted-foreground">{maxWeeksNote}</p>
      )}
    </section>
  )
}

/** 선을 그리기엔 짧은(1~2 point) 시리즈 목록. 선 위에 겹쳐 그리지 않고 별도 줄로 뺀다. */
function AccumulatingNotes({ series }: { series: ChartSeries[] }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-dashed px-4 py-3 text-base leading-relaxed text-muted-foreground">
      {series.map((s) => (
        <span key={s.key}>
          <span className="font-medium text-foreground">{s.label}</span> 데이터 축적 중 ·{' '}
          {validCount(s)}주차
        </span>
      ))}
    </div>
  )
}

/**
 * 그린 것은 있는데 갱신만 실패했다. 차트는 두고 사실만 알린다.
 *
 * **재시도를 권할지는 아래 `MetricError` 와 같은 판단을 쓴다** — `errorNotice` 가
 * 400 계열이라고 하면 버튼을 내지 않는다. 같은 자리에서 판단이 둘로 갈리면
 * `errorNotice` 를 만든 이유가 없어진다.
 */
function RefreshNotice({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const notice = errorNotice(error)

  return (
    <p className="-mt-1.5 flex flex-wrap items-baseline gap-2 text-base leading-relaxed text-muted-foreground">
      <span>최신 자료를 받지 못해 마지막으로 받은 것을 그렸습니다.</span>
      {onRetry && notice.retryable && (
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
 * 이 카드만 실패했을 때. **옆 카드와 패키지 카드는 그대로 남는다.**
 *
 * 재시도도 이 카드만 다시 부른다 — 정상인 옆 지표를 굳이 다시 받을 이유가 없다.
 */
function MetricError({
  height,
  error,
  onRetry,
}: {
  height: number
  error: unknown
  onRetry: () => void
}) {
  const notice = errorNotice(error)
  return (
    <EmptyState height={height}>
      <span className="font-medium text-foreground">{notice.message}</span>
      {notice.code && <span className="font-mono">{notice.code}</span>}
      {notice.retryable && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 rounded-md border px-3 py-1.5 text-xs transition-colors hover:border-foreground/40"
        >
          이 지표만 다시 시도
        </button>
      )}
    </EmptyState>
  )
}

function EmptyState({ height, children }: { height: number; children: React.ReactNode }) {
  return (
    <div
      style={{ height }}
      className="flex flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed px-4 text-center text-base leading-relaxed text-muted-foreground"
    >
      {children}
    </div>
  )
}
