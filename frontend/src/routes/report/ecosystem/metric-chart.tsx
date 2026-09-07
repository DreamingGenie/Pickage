import { sampleEvery, type ChartSeries } from '@/components/charts/geometry'
import { LineChart, SeriesLegend } from '@/components/charts/line-chart'
import { INTERVALS, type SnapshotWindow } from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

/**
 * 지표 하나짜리 독립 카드.
 *
 * 기간·간격은 위 조작줄에서 받아 쓰되, **자를지 말지는 각자 판단한다.**
 * Downloads 는 npm 공식 자료 기준 18개월이 상한이라 그보다 넓은 기간을 고르면
 * 여기서 잘리고, 잘렸다는 사실을 카드 안에서 알린다.
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

  const own = full[0]?.points ?? []
  const ownFirst = own[0]?.t
  /** 고른 시작이 이 지표의 수집 시작보다 앞서면 여기서 잘린다. */
  const clamped = Boolean(ownFirst && window.start < ownFirst)

  const series = full.map((s) => {
    const windowed = s.points.filter((p) => p.t >= window.start && p.t <= window.end)
    return { ...s, points: sampleEvery(windowed, step) }
  })
  const shown = series[0]?.points ?? []

  return (
    <section className={cn('flex min-w-0 flex-col gap-4 rounded-2xl border p-6', className)}>
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="font-mono text-[10.5px] text-muted-foreground">{unit}</span>
      </header>

      {showLegend && <SeriesLegend series={series} emphasisKeys={emphasisKeys} />}

      <LineChart
        series={series}
        height={height}
        emphasisKeys={emphasisKeys}
        observedFrom={observedFrom}
        ariaLabel={`${title} 추이`}
      />

      <div className="flex flex-wrap items-baseline justify-between gap-2 border-t pt-3 text-[10.5px] text-muted-foreground">
        <span className="font-mono">
          {shown.length ? `${shown[0].t} ~ ${shown[shown.length - 1].t}` : '자료 없음'}
        </span>
        <span className="font-mono tabular-nums">
          스냅샷 {shown.length}개{step > 1 && ` · ${step}주 간격`}
        </span>
      </div>

      {clamped && (
        <p className="-mt-1.5 text-[10.5px] leading-relaxed text-muted-foreground">
          {coverageNote ?? '수집된 구간을 넘습니다'} — 이 지표는 {ownFirst} 부터 있어 그 뒤만
          그렸습니다.
        </p>
      )}
    </section>
  )
}
