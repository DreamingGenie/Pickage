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
  scaleYLinear,
  shortDate,
  ticksY,
  ticksYLinear,
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
   * 오른쪽 탭에서 고른 패키지들이 여기로 온다 — 둘 이상 고를 수 있다.
   */
  emphasisKeys?: readonly string[] | null
  /**
   * 이 일수를 넘게 벌어진 이웃 스냅샷은 잇지 않는다(기본 8일 = 주간 수집 + 하루 여유).
   *
   * 화면이 스냅샷을 솎아 그릴 때는 정상 간격 자체가 넓어지므로 부르는 쪽이 올려 준다.
   * 그대로 두면 "4주" 보기에서 모든 구간이 공백으로 판정돼 선이 사라진다.
   */
  maxGapDays?: number
  /**
   * 기본은 로그(311a) — 실제값 그래프에서 자릿수가 다른 시리즈를 겹칠 때 쓴다.
   * 변화율 그래프는 `linear` 를 넘긴다 — 기준이 100 하나뿐이라 압축할 자릿수가 없다.
   */
  yScale?: 'log' | 'linear'
  /**
   * y 도메인을 만드는 방법. 기본은 `extentY` — 그리는 구간의 최솟값·최댓값에서 만든다.
   * 변화율 그래프는 `indexedExtentY` 를 넘긴다(100 을 반드시 포함해야 하는 축이라 이
   * 컴포넌트가 임의로 고르면 안 된다).
   *
   * **도메인 자체가 아니라 함수를 받는다.** 강조가 켜지면 강조된 선만으로 도메인을 다시
   * 만들어야 하는데(아래), 완성된 도메인을 받으면 그 좁히기를 여기서 할 수 없다.
   */
  yDomainOf?: (series: ChartSeries[]) => Domain
  /** y 눈금 라벨. 기본은 `formatTick`(실제값). 변화율은 `formatIndexTick` 을 넘긴다. */
  yFormat?: (v: number, d: Domain) => string
  /** 툴팁 값 표기. 기본은 천 단위 구분. 변화율은 `%` 를 붙인다. */
  valueFormat?: (v: number) => string
  /**
   * 뜻이 있는 가로 기준선. 변화율 그래프의 100% 처럼 **눈금과 무관하게 반드시 보여야 하는**
   * 값에 쓴다. 눈금은 도메인을 균등 분할한 것이라 100 위에 떨어진다는 보장이 없다.
   */
  baseline?: number
  /** 기준선에 붙일 짧은 말. 없으면 선만 긋는다. */
  baselineLabel?: string
  className?: string
  ariaLabel: string
}

const PAD = { t: 8, r: 10, b: 16, l: 34 }

/** y 도메인이 바뀔 때 새 축으로 옮겨 가는 시간(ms). */
const Y_TWEEN_MS = 260

/**
 * 강조가 실제로 갈리는가.
 *
 * `emphasisKeys.length` 와 `series.length` 를 바로 비교하면 안 된다 — **두 집합의 모집단이
 * 다르다.** 강조 목록에는 이 카드가 그리지 못한(자료가 아예 없는) 패키지도 들어 있어서,
 * 그릴 수 있는 시리즈 둘 중 하나만 강조된 상황에서도 `2 < 2` 가 거짓이 되어 강조가 조용히
 * 꺼졌다. 실제로 그렇게 꺼져 있었다. 세어야 하는 것은 **그려지는 시리즈 중 몇 개가 강조
 * 대상인가**다.
 */
function partialEmphasis(
  series: Pick<ChartSeries, 'key'>[],
  emphasisKeys: readonly string[] | null | undefined,
): boolean {
  if (emphasisKeys == null) return false
  let on = 0
  for (const s of series) if (emphasisKeys.includes(s.key)) on++
  return on > 0 && on < series.length
}

/**
 * y 도메인을 한 번에 갈아치우지 않고 몇 프레임에 걸쳐 옮긴다.
 *
 * 구간을 바꾸거나 강조를 켜면 도메인이 통째로 바뀌는데, 그대로 두면 선이 순간이동해
 * 어느 선이 어디로 갔는지 눈으로 따라갈 수 없다. CSS 로는 못 한다 — SVG `path` 의 `d` 는
 * 전이 대상이 아니고, `transform: scaleY()` 로 늘리면 점 크기와 선 굵기까지 같이 찌그러진다.
 * 그래서 도메인 숫자 자체를 rAF 로 보간한다.
 *
 * 움직임을 줄이라는 설정이면 `span = 0` 이라 첫 프레임이 곧 도착점이다 — 효과에서
 * 동기적으로 setState 하지 않으려고 분기 대신 시간으로 처리한다.
 */
function useYDomainTween([lo, hi]: Domain): Domain {
  const [shown, setShown] = useState<Domain>([lo, hi])
  const fromRef = useRef<Domain>([lo, hi])
  const rafRef = useRef(0)

  useEffect(() => {
    const from = fromRef.current
    if (from[0] === lo && from[1] === hi) return
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    const span = reduce ? 0 : Y_TWEEN_MS
    const t0 = performance.now()
    const step = (now: number) => {
      const p = span === 0 ? 1 : Math.min(1, (now - t0) / span)
      const e = 1 - Math.pow(1 - p, 3)
      const next: Domain = [from[0] + (lo - from[0]) * e, from[1] + (hi - from[1]) * e]
      fromRef.current = next
      setShown(next)
      if (p < 1) rafRef.current = requestAnimationFrame(step)
    }
    rafRef.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(rafRef.current)
  }, [lo, hi])

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
  yScale = 'log',
  yDomainOf = extentY,
  yFormat = formatTick,
  valueFormat = (v: number) => v.toLocaleString(),
  baseline,
  baselineLabel,
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

  const xd = extentX(series)

  // 전부 강조하는 건 아무것도 강조하지 않는 것과 같다.
  const partial = partialEmphasis(series, emphasisKeys)
  const isOn = (key: string) => !partial || emphasisKeys!.includes(key)

  /*
    **강조를 켜면 나머지는 흐려지는 것이 아니라 아예 빠진다.**

    흐리기(0.22)로는 부족했다. 증감 그래프에서 자릿수가 작은 패키지의 선은 0 근처에 거의
    수평으로 눕는데, 그게 흐릿한 가로줄이 되어 **기준선처럼 읽힌다** — 실제로 그 오해가
    보고됐다. 눈금선도 0 축도 이미 가로줄이라, 뜻이 다른 가로줄이 하나 더 생기는 셈이다.

    빼는 편이 도메인과도 앞뒤가 맞는다. 도메인을 강조된 선만으로 다시 잡으므로(아래),
    빠진 선들은 어차피 축 밖으로 밀려나 위아래 벽에 눌러 붙은 채 그려진다. 그건 값이
    아니라 잘린 자리에 생긴 그림일 뿐이다.

    무엇이 빠졌는지는 위 칩 줄이 그대로 들고 있다 — 선이 사라져도 목록에서 사라지지 않는다.

    강조 대상이 하나도 그려지지 않았으면(자료가 없어 걸러진 경우) 전체로 물러난다.
    빈 집합이면 축이 [0,1] 로 무너지고 화면이 통째로 빈다.
  */
  const picked = partial ? series.filter((s) => isOn(s.key)) : series
  const drawn = picked.length > 0 ? picked : series
  const yd = useYDomainTween(yDomainOf(drawn))

  const scaleYFn = yScale === 'linear' ? scaleYLinear : scaleY
  const ticksYFn = yScale === 'linear' ? ticksYLinear : ticksY
  const yTicks = bare ? [] : ticksYFn(yd, 3)

  const cutX = observedFrom ? scaleX(ms(observedFrom), xd, box) : null
  const single = drawn.length === 1
  const dot = pointSize(Math.max(...drawn.map((s) => s.points.length), 2), box.w)

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
          const y = scaleYFn(v, yd, box)
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
                {yFormat(v, yd)}
              </text>
            </g>
          )
        })}

        {/*
          뜻이 있는 기준선(변화율 100%).

          눈금선보다 **진하게** 긋는다. 눈금선과 같은 세기면 가로줄 넷 중 하나로 묻혀서,
          "어디가 출발점인가" 를 세어 가며 찾아야 한다. 색도 `--border` 가 아니라
          `--foreground` 를 쓴다 — 점선 하나만으로는 구분이 약했다.

          라벨은 선 위에 얹되 왼쪽 눈금 라벨을 피해 오른쪽 끝에 둔다. 바탕색 테두리를
          둘러 선이 글자를 관통해도 읽힌다.
        */}
        {baseline !== undefined && !bare && baseline >= yd[0] && baseline <= yd[1] && (
          <g>
            <line
              x1={box.x}
              x2={box.x + box.w}
              y1={scaleYFn(baseline, yd, box)}
              y2={scaleYFn(baseline, yd, box)}
              stroke="var(--foreground)"
              strokeWidth="1.5"
              strokeDasharray="5 3"
              strokeOpacity="0.45"
              vectorEffect="non-scaling-stroke"
            />
            {baselineLabel && (
              <text
                x={box.x + box.w - 2}
                y={scaleYFn(baseline, yd, box) - 4}
                textAnchor="end"
                fontSize="9"
                fontWeight="600"
                fill="var(--foreground)"
                fillOpacity="0.6"
                stroke="var(--background)"
                strokeWidth="3"
                paintOrder="stroke"
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {baselineLabel}
              </text>
            )}
          </g>
        )}

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

        {/* 그리는 것은 고른 선뿐이다. 자리 번호가 아니라 `tone` 으로 모양을 고른다 */}
        {drawn.map((s, i) => {
          const st = seriesStyle(s.tone ?? i)
          const focused = partial && drawn.length < series.length
          const hv = hoverT ? (lookup.get(s.key)?.get(hoverT) ?? null) : null
          return (
            <g key={s.key} style={{ transition: 'opacity 200ms ease' }}>
              {(single || focused) && (
                <path
                  d={buildArea(s.points, xd, yd, box, maxGapDays, scaleYFn)}
                  fill={st.color}
                  fillOpacity={0.08}
                />
              )}
              <path
                d={buildLine(s.points, xd, yd, box, maxGapDays, scaleYFn)}
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
                  d={buildPoints(s.points, xd, yd, box, scaleYFn)}
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
                    d={`M${hoverX} ${scaleYFn(hv, yd, box)}L${hoverX} ${scaleYFn(hv, yd, box)}`}
                    stroke="var(--background)"
                    strokeWidth={dot + 7}
                    strokeLinecap="round"
                    vectorEffect="non-scaling-stroke"
                  />
                  <path
                    d={`M${hoverX} ${scaleYFn(hv, yd, box)}L${hoverX} ${scaleYFn(hv, yd, box)}`}
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
            {drawn.map((s, i) => {
              const st = seriesStyle(s.tone ?? i)
              const v = lookup.get(s.key)?.get(hoverT) ?? null
              return (
                <li key={s.key} className="flex items-baseline justify-between gap-4 text-base">
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
                    {v === null ? '자료 없음' : valueFormat(v)}
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
  series: Pick<ChartSeries, 'key' | 'label' | 'tone'>[]
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
