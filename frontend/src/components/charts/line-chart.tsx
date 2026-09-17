import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

import {
  buildArea,
  buildLine,
  buildPoints,
  extentX,
  extentY,
  formatTick,
  MAX_GAP_DAYS,
  ms,
  pointSize,
  scaleX,
  scaleY,
  shortDate,
  ticksY,
  type Box,
  type ChartSeries,
  type Domain,
} from '@/components/charts/geometry'
import { seriesStyle } from '@/components/charts/tokens'
import { cn } from '@/lib/utils'

export interface LineChartProps {
  series: ChartSeries[]
  height?: number
  /** 축·눈금 없이 스파크라인으로만 그린다 */
  bare?: boolean
  /**
   * 관측 시작 시각. 이보다 왼쪽은 "자료 없음"으로 빗금 처리한다.
   * Issues·Stars 는 2022-05-08 이전 관측치가 존재하지 않는다.
   */
  observedFrom?: string
  /**
   * 강조할 시리즈 key 들. 전체를 포함하거나 비어 있으면 아무것도 흐려지지 않는다.
   * 패키지 카드를 접으면 그 선이 차트에서도 물러난다.
   */
  emphasisKeys?: readonly string[] | null
  /**
   * 이 일수를 넘게 벌어진 이웃 스냅샷은 잇지 않는다(기본 8일 = 주간 수집 + 하루 여유).
   *
   * 화면이 스냅샷을 솎아 그릴 때는 정상 간격 자체가 넓어지므로 부르는 쪽이 올려 준다.
   * 그대로 두면 "4주" 보기에서 모든 구간이 공백으로 판정돼 선이 사라진다.
   */
  maxGapDays?: number
  className?: string
  ariaLabel: string
}

const PAD = { t: 8, r: 10, b: 16, l: 34 }

/**
 * 강조가 **실제로 일부만** 가리키는가.
 *
 * <p>강조 목록의 길이를 시리즈 수와 견주면 안 된다. 목록은 패키지 카드가 펼쳐진 것들이고,
 * 여기 들어온 시리즈는 **그릴 수 있는 것만 걸러진 뒤**다(`MetricChart` 가 점이 부족한
 * 시리즈를 뺀다). 둘은 같은 모집단이 아니다.
 *
 * <p>실제로 이렇게 어긋났다 — 세 패키지 중 하나를 접어 강조가 둘인데, 강조된 하나에
 * 자료가 없어 차트에는 둘만 남았다. 그러면 `2 < 2` 가 거짓이라 <b>강조가 통째로 꺼졌고</b>,
 * 남은 하나가 굵어지지 않았다.
 *
 * <p>그래서 **여기 그려지는 시리즈 중 몇이 강조 대상인가**를 센다. 하나도 아니면(전부
 * 접었다) 강조할 것이 없고, 전부면 강조가 아무 뜻이 없다 — 둘 다 평소대로 그린다.
 */
function partialEmphasis(
  series: Pick<ChartSeries, 'key'>[],
  keys: readonly string[] | null,
): boolean {
  if (keys == null) return false
  const on = series.reduce((n, s) => n + (keys.includes(s.key) ? 1 : 0), 0)
  return on > 0 && on < series.length
}

/** 도메인이 바뀔 때 움직이는 시간. 눈으로 따라갈 만큼 짧게. */
const Y_TWEEN_MS = 260

/**
 * y 도메인이 바뀌면 두 끝을 **로그 공간에서** 부드럽게 옮긴다.
 *
 * CSS 로는 못 한다. 선은 `path` 의 `d` 이고 그건 전이 대상이 아니다. 그림 전체에
 * `transform: scaleY()` 를 걸면 축 변화를 정확히 흉내 낼 수는 있다 — 로그 축이라
 * 도메인 변경이 세로 방향 아핀 변환이기 때문이다. 다만 그러면 **점이 타원으로
 * 찌그러지고 선 굵기가 변한다.** 그래서 도메인 숫자를 프레임마다 옮기고 경로를 다시
 * 그린다. 점·선·눈금·격자가 함께 움직인다.
 *
 * 값이 아니라 **로그 값**을 보간하는 것이 중요하다. 축이 로그라서 선형으로 보간하면
 * 화면에서는 급하게 출발해 느리게 도착하는 것처럼 보인다.
 *
 * `prefers-reduced-motion` 이면 곧바로 바꾼다.
 */
function useYDomainTween([lo, hi]: Domain, duration = Y_TWEEN_MS): Domain {
  const [shown, setShown] = useState<Domain>([lo, hi])
  /* 프레임 콜백이 읽는 "지금 그려진 도메인". 렌더에서는 건드리지 않는다. */
  const drawn = useRef<Domain>([lo, hi])

  useEffect(() => {
    const [fromLo, fromHi] = drawn.current
    if (fromLo === lo && fromHi === hi) return

    // 움직임을 줄여 달라고 한 사용자에게는 길이를 0 으로 둔다. 첫 프레임에 도착한다.
    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const span = still ? 0 : duration

    const a0 = Math.log1p(Math.max(0, fromLo))
    const a1 = Math.log1p(Math.max(0, fromHi))
    const b0 = Math.log1p(Math.max(0, lo))
    const b1 = Math.log1p(Math.max(0, hi))
    const began = performance.now()
    let frame = 0

    const step = (now: number) => {
      const p = span <= 0 ? 1 : Math.min(1, (now - began) / span)
      const e = 1 - Math.pow(1 - p, 3) // easeOutCubic — 끝에서 조용히 멈춘다
      const next: Domain =
        p < 1 ? [Math.expm1(a0 + (b0 - a0) * e), Math.expm1(a1 + (b1 - a1) * e)] : [lo, hi]
      drawn.current = next
      setShown(next)
      if (p < 1) frame = requestAnimationFrame(step)
    }

    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [lo, hi, duration])

  return shown
}

/**
 * 여러 패키지의 시계열을 한 카드에 겹쳐 그린다.
 *
 * 끊긴 구간은 선을 잇지 않는다. 없는 관측을 있는 것처럼 만들지 않기 위해서다.
 *
 * 커서를 올리면 가장 가까운 **스냅샷**에 세로선이 서고 그 주의 값이 전부 뜬다.
 * 점마다 히트박스를 두지 않는 이유는 두 가지다 — 점이 촘촘하면 조준이 어렵고,
 * 여러 패키지를 비교하는 화면에서는 같은 시점의 값을 나란히 보는 게 목적이다.
 *
 * 뷰박스를 늘려 채우지 않고 **컨테이너 폭을 실측해 1:1 로** 그린다.
 * preserveAspectRatio="none" 으로 늘리면 축 눈금 글자가 가로로만 퍼져 찌그러진다.
 */
export function LineChart({
  series,
  height = 180,
  bare = false,
  observedFrom,
  emphasisKeys = null,
  maxGapDays = MAX_GAP_DAYS,
  className,
  ariaLabel,
}: LineChartProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [measured, setMeasured] = useState(0)

  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    setMeasured(el.clientWidth)
    const ro = new ResizeObserver(([entry]) => setMeasured(Math.round(entry.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // 1 뷰박스 단위 = 1 화면 픽셀. 늘어나지 않으므로 글자도 원래 비율로 나온다.
  const W = Math.max(measured, 240)
  const H = height
  const pad = bare ? { t: 3, r: 3, b: 3, l: 3 } : PAD
  const box: Box = { x: pad.l, y: pad.t, w: W - pad.l - pad.r, h: H - pad.t - pad.b }

  const partial = partialEmphasis(series, emphasisKeys)
  const isOn = (key: string) => !partial || emphasisKeys!.includes(key)

  /*
    y 범위는 **강조된 시리즈만** 보고 정한다.

    오른쪽 카드를 접어 하나만 남겼는데 흐려진 시리즈가 축을 끝까지 벌리고 있으면,
    남긴 시리즈는 여전히 눌려서 평평하게 보인다. 접는 조작이 "무엇을 볼지" 를 고르는
    일이므로 보이는 범위도 따라와야 한다.

    흐려진 시리즈는 그대로 그린다 — 축 밖으로 나가면 잘리고, 그건 "지금 축은 이 시리즈
    기준" 이라는 뜻이라 오히려 읽힌다.
  */
  const focus = partial ? series.filter((s) => isOn(s.key)) : series
  const xd = extentX(series)
  const yd = useYDomainTween(extentY(focus.length > 0 ? focus : series))
  const yTicks = bare ? [] : ticksY(yd, 3)

  const cutX = observedFrom ? scaleX(ms(observedFrom), xd, box) : null
  const single = series.length === 1
  const dot = pointSize(Math.max(...series.map((s) => s.points.length), 2), box.w)

  /** 스냅샷 시각 목록과 시리즈별 조회표. 커서 위치를 여기에 맞춘다. */
  const { times, lookup } = useMemo(() => {
    const set = new Set<string>()
    const map = new Map<string, Map<string, number | null>>()
    for (const s of series) {
      const m = new Map<string, number | null>()
      for (const p of s.points) {
        set.add(p.t)
        m.set(p.t, p.v)
      }
      map.set(s.key, m)
    }
    return { times: [...set].sort(), lookup: map }
  }, [series])

  const svgRef = useRef<SVGSVGElement>(null)
  const [hover, setHover] = useState<number | null>(null)

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    if (bare || times.length === 0) return
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect || rect.width === 0) return

    // 1:1 이라 화면 좌표를 그대로 쓴다.
    const vx = e.clientX - rect.left
    if (vx < box.x - 8 || vx > box.x + box.w + 8) {
      setHover(null)
      return
    }
    const target = xd[0] + ((vx - box.x) / box.w) * (xd[1] - xd[0])

    let best = 0
    let bestGap = Infinity
    for (let i = 0; i < times.length; i++) {
      const gap = Math.abs(ms(times[i]) - target)
      if (gap < bestGap) {
        bestGap = gap
        best = i
      }
    }
    setHover(best)
  }

  const hoverT = hover !== null ? times[hover] : null
  const hoverX = hoverT ? scaleX(ms(hoverT), xd, box) : null
  /** 툴팁이 오른쪽 벽에 닿으면 왼쪽으로 뒤집는다. */
  const flip = hoverX !== null && hoverX > box.x + box.w * 0.62

  // 첫 렌더에는 폭을 모른다. 높이만 잡아 두고 측정된 뒤에 그린다.
  if (measured === 0) {
    return <div ref={wrapRef} className={cn('w-full', className)} style={{ height: H }} />
  }

  return (
    <div ref={wrapRef} className={cn('relative w-full', className)}>
      <svg
        ref={svgRef}
        role="img"
        aria-label={ariaLabel}
        viewBox={`0 0 ${W} ${H}`}
        width={W}
        height={H}
        className="block touch-none"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        <defs>
          <pattern
            id="pk-nodata"
            width="6"
            height="6"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <rect width="6" height="6" fill="transparent" />
            <line
              x1="0"
              y1="0"
              x2="0"
              y2="6"
              stroke="currentColor"
              strokeWidth="1"
              strokeOpacity="0.18"
            />
          </pattern>
        </defs>

        {/* y 눈금선 */}
        {yTicks.map((v) => {
          const y = scaleY(v, yd, box)
          return (
            <g key={v}>
              <line
                x1={box.x}
                x2={box.x + box.w}
                y1={y}
                y2={y}
                stroke="var(--border)"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
              />
              <text
                x={box.x - 6}
                y={y + 3}
                textAnchor="end"
                fontSize="9"
                fill="var(--muted-foreground)"
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {formatTick(v, yd)}
              </text>
            </g>
          )
        })}

        {/* 관측 시작 이전 — 값이 0 이라는 뜻이 아니라 자료가 없다는 뜻 */}
        {cutX !== null && cutX > box.x + 1 && (
          <g>
            <rect
              x={box.x}
              y={box.y}
              width={cutX - box.x}
              height={box.h}
              fill="url(#pk-nodata)"
              color="var(--muted-foreground)"
            />
            <line
              x1={cutX}
              x2={cutX}
              y1={box.y}
              y2={box.y + box.h}
              stroke="var(--muted-foreground)"
              strokeWidth="1"
              strokeDasharray="3 2"
              vectorEffect="non-scaling-stroke"
            />
          </g>
        )}

        {/* 커서가 붙은 스냅샷 */}
        {hoverX !== null && (
          <line
            x1={hoverX}
            x2={hoverX}
            y1={box.y}
            y2={box.y + box.h}
            stroke="var(--muted-foreground)"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
        )}

        {/* 강조 대상을 나중에 그려 위로 올린다 */}
        {[...series.keys()]
          .sort((a, b) => Number(isOn(series[a].key)) - Number(isOn(series[b].key)))
          .map((i) => {
            const s = series[i]
            const st = seriesStyle(s.tone ?? i)
            const dimmed = partial && !isOn(s.key)
            const focused = partial && isOn(s.key)
            const hv = hoverT ? (lookup.get(s.key)?.get(hoverT) ?? null) : null
            return (
              <g
                key={s.key}
                opacity={dimmed ? 0.22 : 1}
                style={{ transition: 'opacity 200ms ease' }}
              >
                {(single || focused) && (
                  <path
                    d={buildArea(s.points, xd, yd, box, maxGapDays)}
                    fill={st.color}
                    fillOpacity={0.08}
                  />
                )}
                <path
                  d={buildLine(s.points, xd, yd, box, maxGapDays)}
                  fill="none"
                  stroke={st.color}
                  strokeWidth={bare ? 1.6 : focused ? 2.6 : 1.8}
                  strokeDasharray={st.dash}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                />
                {/* 스냅샷 하나에 점 하나. 값이 없는 주는 점도 없다 */}
                {!bare && (
                  <path
                    d={buildPoints(s.points, xd, yd, box)}
                    fill="none"
                    stroke={st.color}
                    strokeWidth={dot + (focused ? 1 : 0)}
                    strokeLinecap="round"
                    vectorEffect="non-scaling-stroke"
                  />
                )}
                {/* 커서가 짚은 점만 키운다 */}
                {hv !== null && hoverX !== null && (
                  <>
                    <path
                      d={`M${hoverX} ${scaleY(hv, yd, box)}L${hoverX} ${scaleY(hv, yd, box)}`}
                      stroke="var(--background)"
                      strokeWidth={dot + 7}
                      strokeLinecap="round"
                      vectorEffect="non-scaling-stroke"
                    />
                    <path
                      d={`M${hoverX} ${scaleY(hv, yd, box)}L${hoverX} ${scaleY(hv, yd, box)}`}
                      stroke={st.color}
                      strokeWidth={dot + 4}
                      strokeLinecap="round"
                      vectorEffect="non-scaling-stroke"
                    />
                  </>
                )}
              </g>
            )
          })}

        {!bare && (
          <>
            <text x={box.x} y={H - 3} fontSize="9" fill="var(--muted-foreground)">
              {shortDate(new Date(xd[0]).toISOString().slice(0, 10))}
            </text>
            <text
              x={box.x + box.w}
              y={H - 3}
              textAnchor="end"
              fontSize="9"
              fill="var(--muted-foreground)"
            >
              {shortDate(new Date(xd[1]).toISOString().slice(0, 10))}
            </text>
          </>
        )}
      </svg>

      {/* 값 툴팁 — SVG 밖 HTML 이라 뷰박스 왜곡을 받지 않는다 */}
      {hoverT && hoverX !== null && (
        <div
          role="status"
          aria-live="polite"
          className="pointer-events-none absolute top-2 z-10 flex min-w-[168px] flex-col gap-1.5 rounded-lg border bg-background px-3 py-2.5 shadow-lg"
          style={flip ? { right: W - hoverX + 10 } : { left: hoverX + 10 }}
        >
          <span className="font-mono text-base text-muted-foreground">{hoverT}</span>
          <ul className="flex flex-col gap-1">
            {series.map((s, i) => {
              const st = seriesStyle(s.tone ?? i)
              const v = lookup.get(s.key)?.get(hoverT) ?? null
              return (
                <li
                  key={s.key}
                  className={cn(
                    'flex items-baseline justify-between gap-4 text-base',
                    partial && !isOn(s.key) && 'opacity-40',
                  )}
                >
                  <span className="flex items-center gap-1.5">
                    <svg width="14" height="8" aria-hidden className="shrink-0">
                      <line
                        x1="0"
                        y1="4"
                        x2="14"
                        y2="4"
                        stroke={st.color}
                        strokeWidth="2"
                        strokeDasharray={st.dash}
                        strokeLinecap="round"
                      />
                    </svg>
                    <span className="font-mono">{s.label}</span>
                  </span>
                  <span
                    className={cn('font-mono tabular-nums', v === null && 'text-muted-foreground')}
                  >
                    {v === null ? '자료 없음' : v.toLocaleString()}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}

/** 그래프 상단 범례. 색과 파선 패턴을 함께 보여준다(IA 8.2 · 1.11). */
export function SeriesLegend({
  series,
  emphasisKeys = null,
  className,
}: {
  series: Pick<ChartSeries, 'key' | 'label'>[]
  emphasisKeys?: readonly string[] | null
  className?: string
}) {
  const partial = partialEmphasis(series, emphasisKeys)
  return (
    <ul className={cn('flex flex-wrap items-center gap-x-4 gap-y-1', className)}>
      {series.map((s, i) => {
        const st = seriesStyle(s.tone ?? i)
        const dimmed = partial && !emphasisKeys!.includes(s.key)
        return (
          <li
            key={s.key}
            className={cn(
              'flex items-center gap-1.5 text-base transition-opacity',
              dimmed && 'opacity-35',
            )}
          >
            <svg width="16" height="8" aria-hidden>
              <line
                x1="0"
                y1="4"
                x2="16"
                y2="4"
                stroke={st.color}
                strokeWidth="2"
                strokeDasharray={st.dash}
                strokeLinecap="round"
              />
            </svg>
            <span className="font-mono">{s.label}</span>
            <span className="sr-only">{st.patternLabel}</span>
          </li>
        )
      })}
    </ul>
  )
}
