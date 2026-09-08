/**
 * 차트 기하 계산. React 를 모르고 DOM 도 모른다.
 *
 * 렌더러(SVG · canvas · uPlot)를 갈아끼워도 이 파일은 그대로 쓴다.
 * 미리보기 스크립트도 같은 함수를 쓰기 때문에 화면과 문서가 어긋나지 않는다.
 */

export interface TimePoint {
  /** ISO8601 date */
  t: string
  /** 관측 실패·미수집 구간은 null 로 보존한다. 0 으로 채우지 않는다(구상안 5.3). */
  v: number | null
}

export interface ChartSeries {
  key: string
  label: string
  points: TimePoint[]
}

export interface Box {
  x: number
  y: number
  w: number
  h: number
}

export type Domain = [number, number]

export const ms = (t: string) => Date.parse(t)

export function extentX(series: ChartSeries[]): Domain {
  let lo = Infinity
  let hi = -Infinity
  for (const s of series) {
    for (const p of s.points) {
      const x = ms(p.t)
      if (x < lo) lo = x
      if (x > hi) hi = x
    }
  }
  return Number.isFinite(lo) ? [lo, hi] : [0, 1]
}

export function extentY(series: ChartSeries[]): Domain {
  let hi = -Infinity
  for (const s of series) {
    for (const p of s.points) {
      if (p.v !== null && p.v > hi) hi = p.v
    }
  }
  // 0 을 항상 포함한다. 잘린 축은 변화를 과장한다.
  return [0, Number.isFinite(hi) ? niceMax(hi) : 1]
}

/** 축 최댓값을 1·2·2.5·5 배수로 올린다. */
export function niceMax(v: number): number {
  if (v <= 0) return 1
  const mag = Math.pow(10, Math.floor(Math.log10(v)))
  const n = v / mag
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10
  return step * mag
}

export function ticksY([lo, hi]: Domain, count = 3): number[] {
  const out: number[] = []
  for (let i = 0; i <= count; i++) out.push(lo + ((hi - lo) * i) / count)
  return out
}

export const scaleX = (v: number, d: Domain, b: Box) =>
  d[1] === d[0] ? b.x : b.x + ((v - d[0]) / (d[1] - d[0])) * b.w

export const scaleY = (v: number, d: Domain, b: Box) =>
  d[1] === d[0] ? b.y + b.h : b.y + b.h - ((v - d[0]) / (d[1] - d[0])) * b.h

/**
 * null 을 만나면 선을 끊는다. 이어 그리면 없는 관측을 있는 것처럼 만든다.
 * 반환은 단일 path d 문자열이며 구간마다 새 M 으로 시작한다.
 */
export function buildLine(points: TimePoint[], xd: Domain, yd: Domain, b: Box): string {
  let d = ''
  let pen = false
  for (const p of points) {
    if (p.v === null) {
      pen = false
      continue
    }
    const x = scaleX(ms(p.t), xd, b).toFixed(2)
    const y = scaleY(p.v, yd, b).toFixed(2)
    d += `${pen ? 'L' : 'M'}${x} ${y}`
    pen = true
  }
  return d
}

/** 선 아래 옅은 면. 끊긴 구간은 면도 끊는다. */
export function buildArea(points: TimePoint[], xd: Domain, yd: Domain, b: Box): string {
  const base = (b.y + b.h).toFixed(2)
  let d = ''
  let run: { x: string; y: string }[] = []

  const flush = () => {
    if (run.length < 2) {
      run = []
      return
    }
    d += `M${run[0].x} ${base}`
    for (const q of run) d += `L${q.x} ${q.y}`
    d += `L${run[run.length - 1].x} ${base}Z`
    run = []
  }

  for (const p of points) {
    if (p.v === null) {
      flush()
      continue
    }
    run.push({
      x: scaleX(ms(p.t), xd, b).toFixed(2),
      y: scaleY(p.v, yd, b).toFixed(2),
    })
  }
  flush()
  return d
}

/**
 * 스냅샷을 step 주 간격으로 솎아 낸다.
 *
 * 값을 평균 내지 않는다. 고른 주의 관측치를 그대로 쓰고 나머지는 화면에서 뺄 뿐이다.
 * 뒤에서부터 세므로 가장 최근 스냅샷은 항상 남는다.
 */
export function sampleEvery(points: TimePoint[], step: number): TimePoint[] {
  if (step <= 1) return points
  const out: TimePoint[] = []
  for (let i = points.length - 1; i >= 0; i -= step) out.push(points[i])
  return out.reverse()
}

/**
 * 스냅샷마다 찍는 점.
 *
 * `<circle>` 을 쓰지 않는 이유: 이 차트는 `preserveAspectRatio="none"` 으로
 * 가로만 늘려 채우기 때문에 원이 타원으로 찌그러진다.
 * 길이 0 짜리 선분에 `stroke-linecap="round"` + `vector-effect="non-scaling-stroke"`
 * 를 주면 뷰박스 왜곡과 무관하게 화면상 정원이 찍힌다.
 */
export function buildPoints(points: TimePoint[], xd: Domain, yd: Domain, b: Box): string {
  let d = ''
  for (const p of points) {
    if (p.v === null) continue
    const x = scaleX(ms(p.t), xd, b).toFixed(2)
    const y = scaleY(p.v, yd, b).toFixed(2)
    d += `M${x} ${y}L${x} ${y}`
  }
  return d
}

/**
 * 점 지름(화면 px). 스냅샷이 촘촘할수록 작게 찍어 선이 뭉개지지 않게 한다.
 * 렌더 폭은 카드 안 기준 약 620px 로 잡는다.
 */
export function pointSize(count: number, assumedWidth = 620): number {
  if (count < 2) return 4
  const spacing = assumedWidth / (count - 1)
  return Math.min(5, Math.max(2.2, spacing * 0.42))
}

/** 도넛 한 조각. 각도는 12시에서 시작해 시계 방향. */
export function donutArc(
  cx: number,
  cy: number,
  rOuter: number,
  rInner: number,
  startFrac: number,
  endFrac: number,
): string {
  const TAU = Math.PI * 2
  const a0 = startFrac * TAU - Math.PI / 2
  const a1 = endFrac * TAU - Math.PI / 2
  const large = a1 - a0 > Math.PI ? 1 : 0
  const pt = (r: number, a: number) => [cx + r * Math.cos(a), cy + r * Math.sin(a)] as const
  const [x0, y0] = pt(rOuter, a0)
  const [x1, y1] = pt(rOuter, a1)
  const [x2, y2] = pt(rInner, a1)
  const [x3, y3] = pt(rInner, a0)
  return (
    `M${x0.toFixed(2)} ${y0.toFixed(2)}` +
    `A${rOuter} ${rOuter} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}` +
    `L${x2.toFixed(2)} ${y2.toFixed(2)}` +
    `A${rInner} ${rInner} 0 ${large} 0 ${x3.toFixed(2)} ${y3.toFixed(2)}Z`
  )
}

export function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}k`
  return String(Math.round(n))
}

export const shortDate = (t: string) => t.slice(2, 7).replace('-', '.')
