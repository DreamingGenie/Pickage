import { sampleEvery, type ChartSeries } from '@/components/charts/geometry'
import { LineChart, SeriesLegend } from '@/components/charts/line-chart'
import {
  INTERVALS,
  MIN_POINTS_FOR_LINE,
  type SnapshotWindow,
} from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

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
  series: full,
  window,
  intervalKey,
  observedFrom,
  coverageNote,
  emphasisKeys = null,
  height = 192,
  showLegend = false,
  className,
}: {
  title: string
  unit: string
  series: ChartSeries[]
  window: SnapshotWindow
  intervalKey: string
  observedFrom?: string
  coverageNote?: string
  emphasisKeys?: readonly string[] | null
  height?: number
  showLegend?: boolean
  className?: string
}) {
  const step = INTERVALS.find((i) => i.key === intervalKey)?.step ?? 1

  /** 고른 시작이 이 지표의 관측 시작보다 앞서면 여기서 잘린다. */
  const clamped = Boolean(observedFrom && window.start < observedFrom)

  const series = full.map((s) => {
    const windowed = s.points.filter((p) => p.t >= window.start && p.t <= window.end)
    return { ...s, points: sampleEvery(windowed, step) }
  })

  /** 가장 긴 시리즈 기준으로 본다. 짧은 시리즈 하나 때문에 전체를 막지 않는다. */
  const maxPoints = Math.max(0, ...series.map((s) => s.points.length))
  const allDates = [...new Set(series.flatMap((s) => s.points.map((p) => p.t)))].sort()
  const accumulating = maxPoints > 0 && maxPoints < MIN_POINTS_FOR_LINE

  return (
    <section className={cn('flex min-w-0 flex-col gap-4 rounded-2xl border p-6', className)}>
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="font-mono text-[10.5px] text-muted-foreground">{unit}</span>
      </header>

      {showLegend && <SeriesLegend series={series} emphasisKeys={emphasisKeys} />}

      {maxPoints === 0 ? (
        <EmptyState height={height}>이 구간에 관측된 스냅샷이 없습니다.</EmptyState>
      ) : accumulating ? (
        /*
          점 두 개를 선으로 이으면 없는 추세를 그린 것이 된다.
          관측치는 숨기지 않고 그대로 적되, 선은 그리지 않는다.
        */
        <EmptyState height={height}>
          <span className="font-medium text-foreground">데이터 축적 중 · {maxPoints}주차</span>
          <span>
            추세를 그리려면 스냅샷이 {MIN_POINTS_FOR_LINE}개 이상 필요합니다. 현재 관측:{' '}
            <span className="font-mono">{allDates.join(', ')}</span>
          </span>
        </EmptyState>
      ) : (
        <LineChart
          series={series}
          height={height}
          emphasisKeys={emphasisKeys}
          observedFrom={observedFrom}
          ariaLabel={`${title} 추이`}
        />
      )}

      <div className="flex flex-wrap items-baseline justify-between gap-2 border-t pt-3 text-[10.5px] text-muted-foreground">
        <span className="font-mono">
          {allDates.length ? `${allDates[0]} ~ ${allDates[allDates.length - 1]}` : '자료 없음'}
        </span>
        <span className="font-mono tabular-nums">
          스냅샷 {maxPoints}개{step > 1 && ` · ${step}주 간격`}
        </span>
      </div>

      {clamped && (
        <p className="-mt-1.5 text-[10.5px] leading-relaxed text-muted-foreground">
          {coverageNote ?? '수집된 구간을 넘습니다'} — 이 지표는 {observedFrom} 부터 있어 그 뒤만
          그렸습니다.
        </p>
      )}
    </section>
  )
}

function EmptyState({ height, children }: { height: number; children: React.ReactNode }) {
  return (
    <div
      style={{ height }}
      className="flex flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed px-4 text-center text-[11.5px] leading-relaxed text-muted-foreground"
    >
      {children}
    </div>
  )
}
