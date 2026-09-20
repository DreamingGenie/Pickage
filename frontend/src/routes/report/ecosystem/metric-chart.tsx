import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { CircleAlertIcon } from 'lucide-react'

import {
  formatIndexTick,
  INDEX_BASE,
  indexedExtentY,
  indexSeriesTo100,
  type ChartSeries,
} from '@/components/charts/geometry'
import { LineChart, SeriesLegend } from '@/components/charts/line-chart'
import { errorNotice } from '@/api/client'
import { InfoDialog } from '@/components/common/info-dialog'
import { SegmentedControl } from '@/components/common/segmented-control'
import {
  MIN_POINTS_FOR_LINE,
  type MetricState,
  type SnapshotWindow,
} from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

/** 실제값이냐 구간 시작 대비 변화율이냐. */
type ScaleMode = 'absolute' | 'index'

/** 툴팁에 찍을 변화율. 소수 한 자리면 "103.4%" 처럼 읽을 것이 남는다. */
function formatPercent(v: number): string {
  return `${v.toFixed(1)}%`
}

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
  info,
  infoTitle,
  fill = false,
  emphasisKeys = null,
  height = 192,
  showLegend = false,
  state = { status: 'ready' },
  allowIndex = true,
  defaultScale = 'absolute',
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
  /**
   * 제목 옆 ⓘ 모달의 본문. 카드에 상시 노출하기엔 길지만 읽는 사람이 궁금해할 설명을 여기 둔다
   * (S15P21A506-405). 관측 시작 안내는 넘기지 않아도 **이 카드가 스스로 덧붙인다** — 구간이
   * 이 지표의 관측 시작보다 앞서 잘렸을 때만 의미가 있는 문장이라서다.
   */
  info?: ReactNode
  /** 모달 제목. 없으면 카드 제목을 쓴다. */
  infoTitle?: string
  /**
   * 부모가 준 높이를 채운다. 좌우 열의 높이를 맞추려고 카드가 늘어나면 그래프도 함께 커진다 —
   * 그렇지 않으면 카드만 커지고 안에 빈 자리가 생긴다. `height` 는 이때 **최솟값**이다.
   */
  fill?: boolean
  emphasisKeys?: readonly string[] | null
  height?: number
  showLegend?: boolean
  /** 이 카드만의 처지. 옆 카드와 섞이지 않는다. */
  state?: MetricState
  /** "실제값·변화율" 토글을 낼지. 인트로 미리보기처럼 조작이 없는 자리는 끈다. */
  allowIndex?: boolean
  /**
   * 처음 보여 줄 모드. 기본은 실제값이다. 한때 Dependents 를 `index`(변화율)로 열었으나(S15P21A506-403)
   * 실제값이 기본으로 되돌아왔다(S15P21A506-416).
   * `allowIndex` 가 꺼져 있으면 무시된다 — 토글이 없는 카드가 변화율로 열리면 되돌릴 방법이 없다.
   */
  defaultScale?: ScaleMode
  className?: string
}) {
  /** 고른 시작이 이 지표의 관측 시작보다 앞서면 여기서 잘린다. */
  const clamped = Boolean(observedFrom && window.start < observedFrom)
  /** 관측 시작 안내는 잘렸을 때만 뜬다. 자료를 받는 중이거나 실패했을 때는 말할 것이 없다. */
  const showClampNote = state.status === 'ready' && clamped
  const hasInfo = Boolean(info) || showClampNote

  /**
   * 기본은 실제값이고, 부르는 쪽이 `defaultScale` 로 바꿀 수 있다. 변화율은 토글로 전환한다 —
   * 규모가 다른 패키지를 나란히 놓고 "누가 더 빨리 늘었나" 를 볼 때 쓴다.
   *
   * 변화율은 **구간 시작을 100% 로 두고 그 대비 비율**을 그린다. 규모가 다른 패키지를 같은
   * 축에서 비교하려는 쪽의 답이다 — 의존 수 300 짜리와 3만짜리가 둘 다 100 에서 출발하므로
   * 성장 속도만 남는다.
   */
  const [scaleMode, setScaleMode] = useState<ScaleMode>(defaultScale)
  const showingIndex = allowIndex && scaleMode === 'index'

  /** 공백 판정 기준을 지금 보고 있는 간격에 맞춘다(아래 LineChart 호출부와 같은 식·같은 이유). */
  const maxGapDays = step * 7 + 1

  /**
   * 실제값은 원본 그대로 로그축에, 변화율은 100 기준으로 환산해 선형축에 그린다.
   * 변화율 축만 도메인을 넘기는 이유는 100 이 반드시 화면 안에 있어야 하기 때문이다 —
   * 실제값 축은 `extentY` 가 구간의 최솟값·최댓값에서 알아서 만든다.
   *
   * **환산은 이미 잘린 시리즈를 받아서 한다.** 부르는 쪽(`EcosystemView`)이 구간·간격을
   * 적용한 것을 넘기므로, 여기서 잡는 기준값은 화면에 실제로 뜬 첫 점이다.
   */
  const displaySeries = useMemo(
    () => (showingIndex ? indexSeriesTo100(series) : series),
    [series, showingIndex],
  )

  const yScale: 'log' | 'linear' = showingIndex ? 'linear' : 'log'
  // 도메인을 여기서 계산하지 않고 만드는 법만 넘긴다 — 강조가 켜지면 차트가 강조된
  // 선만으로 다시 만들어야 하고, 그건 어느 선이 강조됐는지 아는 쪽에서만 할 수 있다.
  const yDomainOf = showingIndex ? indexedExtentY : undefined

  const modeLabel = showingIndex ? '변화율 · 구간 시작 = 100%' : '로그축'
  const ariaSuffix = showingIndex
    ? '변화율 — 표시 구간의 첫 관측치를 100%로 두고 그 대비 비율로 그렸습니다'
    : '로그축 — 세로 간격이 아니라 눈금 값을 읽어 주세요'

  /**
   * **시리즈별로** 선을 그릴지 가른다(311b) — 예전에는 가장 긴 시리즈 하나로 카드 전체를
   * gate 해서, 짧은 시리즈 하나가 다른 시리즈들 옆에 추세인 것처럼 그대로 그려졌다.
   * "관측 행이 있는가"(raw)와 "그릴 값이 있는가"(valid, null 제외)도 구분한다.
   *
   * 변화율 모드에서는 기준값이 없거나 0 인 시리즈가 통째로 결측이 된다 — 그래서 이 판정도
   * `displaySeries`(환산 후)를 보고 다시 한다.
   */
  const rawMax = Math.max(0, ...displaySeries.map((s) => s.points.length))

  const lined = displaySeries.filter((s) => validCount(s) >= MIN_POINTS_FOR_LINE)
  const accumulating = displaySeries.filter((s) => {
    const c = validCount(s)
    return c > 0 && c < MIN_POINTS_FOR_LINE
  })

  return (
    <section className={cn('flex min-w-0 flex-col gap-4 rounded-2xl border p-6', className)}>
      {/*
        머리글은 제목과 토글뿐이다. 단위·축 종류·구간·스냅샷 개수를 늘어놓던 줄은 전부
        뺐다 — 읽는 사람이 쓰는 정보가 아니라 화면을 만든 쪽의 사정이었다. 대신 제목의
        `title` 속성에 남겨 두어 필요하면 확인할 수 있게 한다.
      */}
      {/*
        min-h-10: 토글이 있는 카드(의존 수)와 없는 카드(Downloads)의 머리글 높이가 달라 두 카드가 자연
        높이에서 13px 어긋났다. 최솟값을 맞춰 두 카드가 언제나 같은 높이가 되게 한다(S15P21A506-405).
      */}
      <header className="flex min-h-10 flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold" title={`${unit} · ${modeLabel}`}>
            {title}
          </h3>
          {hasInfo && (
            <InfoDialog label={`${title} 안내`} title={infoTitle ?? title}>
              {info}
              {showClampNote && (
                <p>
                  이 지표는 {observedFrom}부터 관측되어, 고른 조회 기간 중 그 이전 구간은 그리지
                  않았습니다.
                </p>
              )}
            </InfoDialog>
          )}
        </div>
        {allowIndex && (
          <SegmentedControl
            label={`${title} 실제값·변화율 전환`}
            options={[
              { key: 'absolute', label: '실제값' },
              { key: 'index', label: '변화율' },
            ]}
            value={scaleMode}
            onChange={(key) => setScaleMode(key as ScaleMode)}
          />
        )}
      </header>

      {showLegend && state.status === 'ready' && (
        <SeriesLegend series={series} emphasisKeys={emphasisKeys} />
      )}

      <ChartArea fill={fill} minHeight={height}>
        {(h) =>
          state.status === 'loading' ? (
            <ChartLoading height={h} />
          ) : state.status === 'error' ? (
            <MetricError height={h} error={state.error} onRetry={state.onRetry} />
          ) : rawMax === 0 ? (
            <EmptyState height={h}>이 구간에 관측된 스냅샷이 없습니다.</EmptyState>
          ) : lined.length === 0 ? (
            /*
            점 두 개를 선으로 이으면 없는 추세를 그린 것이 된다. 시리즈 전부가 이 상태라
            그릴 선이 하나도 없다 — 관측치는 숨기지 않고 그대로 적되, 선은 그리지 않는다.
          */
            <EmptyState height={h} icon={false}>
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
                height={h}
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
                maxGapDays={maxGapDays}
                yScale={yScale}
                yDomainOf={yDomainOf}
                yFormat={showingIndex ? formatIndexTick : undefined}
                valueFormat={showingIndex ? formatPercent : undefined}
                baseline={showingIndex ? INDEX_BASE : undefined}
                baselineLabel={showingIndex ? '구간 시작 100%' : undefined}
                ariaLabel={`${title} 추이 (${ariaSuffix})`}
              />
            </>
          )
        }
      </ChartArea>
      {/* 선을 그리기엔 짧은 시리즈가 옆에 남아 있으면 숨기지 않고 따로 알린다(311b) */}
      {state.status === 'ready' && lined.length > 0 && accumulating.length > 0 && (
        <AccumulatingNotes series={accumulating} />
      )}

      {state.status === 'ready' && state.refreshError !== undefined && (
        <RefreshNotice error={state.refreshError} onRetry={state.onRetry} />
      )}
    </section>
  )
}

/**
 * 그래프가 그려지는 자리.
 *
 * `fill` 이 꺼져 있으면 `minHeight` 그대로다. 켜져 있으면 카드가 늘어난 만큼 이 자리도 늘어나고,
 * **실제로 얼마나 늘었는지 재서** 안의 그래프에 넘긴다.
 *
 * 안쪽을 `absolute` 로 띄우는 것이 핵심이다. 그래프가 자기 높이로 이 자리를 밀면, 한 번 커진 카드가
 * 줄어들 이유를 잃는다 — 화면을 넓혀 오른쪽 카드가 짧아져도 왼쪽이 예전 높이를 붙들고 있게 된다.
 * 띄워 두면 이 자리의 높이는 오직 바깥(카드·그리드)이 정한다.
 */
function ChartArea({
  fill,
  minHeight,
  children,
}: {
  fill: boolean
  minHeight: number
  children: (height: number) => ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [measured, setMeasured] = useState(minHeight)

  useLayoutEffect(() => {
    const el = ref.current
    if (!fill || !el || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => {
      setMeasured(Math.max(minHeight, Math.floor(entry.contentRect.height)))
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [fill, minHeight])

  if (!fill) return <>{children(minHeight)}</>
  return (
    <div ref={ref} className="relative flex-1" style={{ minHeight }}>
      <div className="absolute inset-0">{children(Math.max(minHeight, measured))}</div>
    </div>
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

/**
 * 그릴 것이 없을 때 자리를 지키는 판.
 *
 * 반투명한 바탕과 물음표 아이콘을 둔다 — 테두리만 점선인 빈 칸은 "아직 안 그렸나"
 * 처럼 보여서, 자료를 못 받았다는 사실이 전달되지 않았다. 축적 중처럼 실패가 아닌
 * 경우에는 `icon={false}` 로 아이콘만 뺀다.
 */
function EmptyState({
  height,
  icon = true,
  children,
}: {
  height: number
  icon?: boolean
  children: React.ReactNode
}) {
  return (
    <div
      style={{ height }}
      className="flex flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed bg-muted/40 px-4 text-center text-base leading-relaxed text-muted-foreground"
    >
      {icon && <CircleAlertIcon aria-hidden className="size-5 opacity-50" />}
      {children}
    </div>
  )
}

/**
 * 불러오는 동안의 차트 자리.
 *
 * 회색 사각형 하나를 두면 다음에 올 것이 무엇인지 알 수 없어 화면이 한 번 덜컥인다.
 * 눈금선과 선 하나를 미리 같은 자리에 그려 두면 자료가 도착했을 때 바뀌는 것은 선의
 * 모양뿐이다.
 */
function ChartLoading({ height }: { height: number }) {
  return (
    <div className="w-full animate-pulse" style={{ height }} aria-hidden>
      <svg
        viewBox="0 0 320 100"
        preserveAspectRatio="none"
        className="size-full text-muted-foreground/25"
      >
        {[20, 45, 70, 95].map((y) => (
          <line key={y} x1="0" x2="320" y1={y} y2={y} stroke="currentColor" strokeWidth="1" />
        ))}
        <path
          d="M0 82C40 78 60 60 100 56S160 62 200 44S270 26 320 18"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      </svg>
    </div>
  )
}
