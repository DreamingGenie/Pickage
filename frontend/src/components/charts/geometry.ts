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
  /**
   * 선 모양·색을 고르는 자리 번호 (`seriesStyle`).
   *
   * **배열에서의 위치가 아니라 시리즈에 붙은 값이다.** 위치로 정하면 그릴 수 없는
   * 시리즈 하나를 걸러낸 순간 뒤의 것들이 한 칸씩 밀려, 카드·범례에 그린 선과 차트의
   * 선이 어긋난다. 실제로 그렇게 어긋나 있었다.
   *
   * 값은 **최종 비교 순서**(IA 11.1)다 — 0 번이 기준 패키지.
   */
  tone?: number
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

/**
 * y축은 로그 공간에서 그린다(311a). 의존 수·다운로드 모두 몇 자릿수를 오가서, 선형 축이면
 * 큰 시리즈 옆에서 작은 시리즈가 바닥에 눌려 붙는다. `log1p`를 쓰는 이유는 하한이 0 일 수
 * 있어서다 — `log(0)`은 `-Infinity`지만 `log1p(0) = 0`이라 0이 바닥에 안전하게 찍힌다.
 */
const toLog = (v: number) => Math.log1p(Math.max(0, v))

/** 도메인 양끝에 두는 여백. 선이 축선에 붙지 않을 만큼만 준다. */
const Y_PAD = 0.08
/** 여백이 선형 값 기준으로 이만큼을 넘지 않게 한다. */
const Y_PAD_CLAMP = 0.15

/**
 * 절대값 y 도메인. **화면에 그리는 구간의 최솟값·최댓값에서 만든다.**
 *
 * 예전에는 하한을 0 으로 못 박았다("잘린 축은 변화를 과장한다"). 막대처럼 절대량을
 * 읽는 그림에서는 맞는 원칙이지만, 여기는 <b>구간을 골라 추세를 보는 선그래프</b>다.
 * 의존 수가 98만에서 102만으로 움직여도 도메인이 [0, 1M] 이면 선이 세로폭의 0.3% 만
 * 쓰고 <b>일자로 보인다</b> — 실측이다. 구간을 좁히는 조작 자체가 무의미해진다.
 *
 * <p>대신 축 눈금이 0 에서 시작하지 않는다는 사실이 <b>눈금 라벨에 그대로 드러난다.</b>
 * 맨 아래 라벨이 0 이 아닌 것을 읽는 사람이 본다. 축을 따로 잘랐다고 표시하지 않는 것은
 * 그 때문이다 — 숨긴 것이 없다.
 *
 * <p>여백은 로그 공간에서 8% 주되 선형 값 기준 15% 로 자른다. 자르지 않으면 몇 자릿수를
 * 오가는 시리즈에서 위쪽 여백이 폭발한다 — 최대 98만인 자료에 1.7M 눈금이 붙는다.
 */
export function extentY(series: ChartSeries[]): Domain {
  let lo = Infinity
  let hi = -Infinity
  for (const s of series) {
    for (const p of s.points) {
      if (p.v === null) continue
      if (p.v < lo) lo = p.v
      if (p.v > hi) hi = p.v
    }
  }
  if (!Number.isFinite(hi) || hi <= 0) return [0, 1]

  // 값이 하나뿐이면 구간이 없다. 평평한 선을 가운데 두고 위아래로 벌린다.
  if (lo === hi) {
    const margin = Math.max(1, hi * 0.1)
    return [Math.max(0, hi - margin), hi + margin]
  }

  const lLo = toLog(lo)
  const lHi = toLog(hi)
  const pad = (lHi - lLo) * Y_PAD
  const top = Math.min(Math.expm1(lHi + pad), hi * (1 + Y_PAD_CLAMP))
  // 자료가 0 에 닿으면 하한도 0 이다. log1p(0) = 0 이라 바닥에 안전하게 찍힌다.
  const bottom = lo <= 0 ? 0 : Math.max(Math.expm1(Math.max(0, lLo - pad)), lo * (1 - Y_PAD_CLAMP))
  return [bottom, top]
}

/** 축 최댓값을 1·2·2.5·5 배수로 올린다. */
export function niceMax(v: number): number {
  if (v <= 0) return 1
  const mag = Math.pow(10, Math.floor(Math.log10(v)))
  const n = v / mag
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10
  return step * mag
}

/** `niceMax` 의 부호 있는 버전. 증감 축의 아래쪽(음수) 여유를 같은 규칙으로 올린다. */
function niceBound(v: number): number {
  if (v === 0) return 0
  return v < 0 ? -niceMax(-v) : niceMax(v)
}

/**
 * 증감(전 스냅샷 대비 순증감) 그래프의 도메인. **0 은 항상 포함한다** — 여기서 0 은 임의의
 * 바닥이 아니라 "변화 없음"이라는 실제 기준선이다. 증가와 감소가 같은 그림 안에서 부호로
 * 갈리려면 0 이 화면 안에 있어야 한다. 위아래 모두 `niceMax` 로 올려 음수 구간도 대칭적으로
 * 여유를 둔다.
 */
export function deltaExtentY(series: ChartSeries[]): Domain {
  let lo = 0
  let hi = 0
  for (const s of series) {
    for (const p of s.points) {
      if (p.v === null) continue
      if (p.v < lo) lo = p.v
      if (p.v > hi) hi = p.v
    }
  }
  return [niceBound(lo), niceBound(hi)]
}

/**
 * 눈금 값. 로그 공간에서 고르게 나눈다 — 축이 로그이므로 화면에서도 고르게 놓인다.
 *
 * <p>값이 1000 미만이면 정수로 반올림하고 중복을 없앤다. 의존 수·다운로드는 정수라
 * "0.9 · 1.5 · 2.2" 같은 눈금이 뜻을 갖지 않고, 반올림하면 같은 값이 겹치기 때문이다.
 * 남는 눈금이 둘도 안 되면 반올림을 포기하고 원래 값을 쓴다.
 */
export function ticksY([lo, hi]: Domain, count = 3): number[] {
  const lLo = toLog(lo)
  const lHi = toLog(hi)
  const out: number[] = []
  for (let i = 0; i <= count; i++) out.push(Math.expm1(lLo + ((lHi - lLo) * i) / count))
  if (hi >= 1000) return out
  const unique = [...new Set(out.map(Math.round))]
  return unique.length >= 2 ? unique : out
}

/** 증감처럼 선형 공간이 맞는 축의 눈금. 로그 변환을 거치지 않는다. */
export function ticksYLinear([lo, hi]: Domain, count = 3): number[] {
  const out: number[] = []
  for (let i = 0; i <= count; i++) out.push(lo + ((hi - lo) * i) / count)
  return out
}

/**
 * y 눈금 라벨.
 *
 * <p>도메인이 좁으면 `compact` 로는 눈금이 겹친다 — 98만~102만 구간에서 1,000,000 과
 * 1,013,000 이 둘 다 "1.0M" 이 된다. 그때만 단위를 축 전체로 고정하고 소수 자리를
 * 눈금 간격에 맞춘다. 한 자릿수 넘게 벌어진 축은 눈금마다 자릿수가 달라야 읽히므로
 * `compact` 를 그대로 쓴다.
 *
 * <p>증감 축은 음수가 나온다 — 부호를 떼고 크기만 재서 자릿수를 고른 뒤 다시 붙인다.
 */
export function formatTick(v: number, [lo, hi]: Domain, count = 3): string {
  const span = Math.max(Math.abs(lo), Math.abs(hi))
  const sign = v < 0 ? '-' : ''
  const a = Math.abs(v)
  if (lo > 0 && hi / lo < 10) {
    const unit = hi >= 1_000_000 ? 1_000_000 : hi >= 1_000 ? 1_000 : 1
    const suffix = unit === 1_000_000 ? 'M' : unit === 1_000 ? 'k' : ''
    const step = (hi - lo) / count / unit
    const decimals = step >= 1 ? 0 : step >= 0.1 ? 1 : step >= 0.01 ? 2 : 3
    return `${(v / unit).toFixed(decimals)}${suffix}`
  }
  return span === 0 ? '0' : `${sign}${compact(a)}`
}

export const scaleX = (v: number, d: Domain, b: Box) =>
  d[1] === d[0] ? b.x : b.x + ((v - d[0]) / (d[1] - d[0])) * b.w

/**
 * 값·도메인 양끝을 로그 공간으로 옮긴 뒤 선형 보간한다. 변환이 여기 안에 갇혀 있어서
 * `buildLine`/`buildArea`/`buildPoints`는 `scaleY`를 통해서만 좌표를 얻는 한 그대로 쓸 수 있다.
 */
export const scaleY = (v: number, d: Domain, b: Box) => {
  const lLo = toLog(d[0])
  const lHi = toLog(d[1])
  return lHi === lLo ? b.y + b.h : b.y + b.h - ((toLog(v) - lLo) / (lHi - lLo)) * b.h
}

/**
 * 로그 없이 그대로 선형 보간한다. 증감 그래프에 쓴다 — 음수가 나올 수 있고 로그는 음수를
 * 정의하지 못한다.
 */
export const scaleYLinear = (v: number, d: Domain, b: Box) =>
  d[1] === d[0] ? b.y + b.h : b.y + b.h - ((v - d[0]) / (d[1] - d[0])) * b.h

/**
 * 관측 공백으로 볼 간격의 기본값(일).
 *
 * 수집은 주 1회이므로 정상 간격은 7일이다. 8일을 넘으면 그 사이 주를 못 받은 것이다
 * (`DEC-RECONCILIATION-20260910-01` 7번). 하루의 여유는 수집 시각이 밀리는 경우를 위한 것이다.
 */
export const MAX_GAP_DAYS = 8

const DAY_MS = 86_400_000

/**
 * 선을 끊어야 하는가.
 *
 * **값이 `null` 인 경우와 행 자체가 없는 경우는 다르다.** 앞은 서버가 "관측했으나 값이
 * 없다" 고 말한 것이고, 뒤는 아무 말도 하지 않은 것이다. 지금까지는 앞만 끊었기 때문에,
 * 주간 수집이 통째로 빠진 구간이 양옆을 잇는 직선으로 그려져 **연속 관측처럼 보였다.**
 *
 * 원인을 단정하지 않는다 — 수집 실패인지 그 주에 스냅샷을 만들지 않은 것인지 화면은
 * 알 수 없다. 그저 잇지 않을 뿐이다.
 */
const broken = (prev: TimePoint | null, cur: TimePoint, maxGapDays: number) =>
  prev !== null && ms(cur.t) - ms(prev.t) > maxGapDays * DAY_MS

/**
 * null 을 만나거나 간격이 벌어지면 선을 끊는다. 이어 그리면 없는 관측을 있는 것처럼 만든다.
 * 반환은 단일 path d 문자열이며 구간마다 새 M 으로 시작한다.
 *
 * @param maxGapDays 이 일수를 넘게 벌어진 이웃은 잇지 않는다. 화면이 스냅샷을 솎아 그릴
 *                   때는(`sampleEvery`) 정상 간격 자체가 넓어지므로 호출하는 쪽이 그 간격에
 *                   맞춰 올려 준다. 안 그러면 4주 간격 보기에서 모든 구간이 끊긴다.
 * @param yScaleFn   기본은 로그(`scaleY`). 지수·증감 그래프는 `scaleYLinear` 를 넘긴다.
 */
export function buildLine(
  points: TimePoint[],
  xd: Domain,
  yd: Domain,
  b: Box,
  maxGapDays: number = MAX_GAP_DAYS,
  yScaleFn: (v: number, d: Domain, b: Box) => number = scaleY,
): string {
  let d = ''
  let pen = false
  let prev: TimePoint | null = null
  for (const p of points) {
    if (p.v === null) {
      pen = false
      prev = null
      continue
    }
    if (broken(prev, p, maxGapDays)) pen = false
    const x = scaleX(ms(p.t), xd, b).toFixed(2)
    const y = yScaleFn(p.v, yd, b).toFixed(2)
    d += `${pen ? 'L' : 'M'}${x} ${y}`
    pen = true
    prev = p
  }
  return d
}

/** 선 아래 옅은 면. 끊긴 구간은 면도 끊는다 — 선과 같은 판정을 쓴다. */
export function buildArea(
  points: TimePoint[],
  xd: Domain,
  yd: Domain,
  b: Box,
  maxGapDays: number = MAX_GAP_DAYS,
  yScaleFn: (v: number, d: Domain, b: Box) => number = scaleY,
): string {
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

  let prev: TimePoint | null = null
  for (const p of points) {
    if (p.v === null) {
      flush()
      prev = null
      continue
    }
    if (broken(prev, p, maxGapDays)) flush()
    run.push({
      x: scaleX(ms(p.t), xd, b).toFixed(2),
      y: yScaleFn(p.v, yd, b).toFixed(2),
    })
    prev = p
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
 * 표시 구간으로 자르고 간격만큼 솎는다. 카드마다 각자 하면 같은 계산이 두 번 일어나고,
 * 증감(`deltaOf`)이 이 결과가 아닌 원본 시리즈를 보고 계산되는 일이 생긴다(311c) —
 * 그래서 화면이 그리는 시리즈와 증감을 세는 시리즈가 **항상 같은 함수의 결과**이게 한다.
 */
export function windowSeries(
  series: ChartSeries[],
  start: string,
  end: string,
  step: number,
): ChartSeries[] {
  return series.map((s) => {
    const windowed = s.points.filter((p) => p.t >= start && p.t <= end)
    return { ...s, points: sampleEvery(windowed, step) }
  })
}

/**
 * 스냅샷마다 찍는 점.
 *
 * `<circle>` 을 쓰지 않는 이유: 이 차트는 `preserveAspectRatio="none"` 으로
 * 가로만 늘려 채우기 때문에 원이 타원으로 찌그러진다.
 * 길이 0 짜리 선분에 `stroke-linecap="round"` + `vector-effect="non-scaling-stroke"`
 * 를 주면 뷰박스 왜곡과 무관하게 화면상 정원이 찍힌다.
 */
export function buildPoints(
  points: TimePoint[],
  xd: Domain,
  yd: Domain,
  b: Box,
  yScaleFn: (v: number, d: Domain, b: Box) => number = scaleY,
): string {
  let d = ''
  for (const p of points) {
    if (p.v === null) continue
    const x = scaleX(ms(p.t), xd, b).toFixed(2)
    const y = yScaleFn(p.v, yd, b).toFixed(2)
    d += `M${x} ${y}L${x} ${y}`
  }
  return d
}

/**
 * 화면에 그려진(windowed+sampled) 연속 점끼리의 차이(증감 모드).
 *
 * **부르는 쪽은 반드시 화면에 그린 것과 같은 시리즈를 넘겨야 한다** — `deltaOf`(311c)와
 * 같은 이유다. 표시 간격을 4주로 솎아 보고 있으면 이 함수가 만드는 것도 "4주 간격 증감"이고,
 * 그게 화면 x축이 실제로 보여주는 간격과 일치한다.
 *
 * 결측이거나 이웃과 너무 벌어진(`maxGapDays` 초과) 점은 증감을 셀 수 없다 — 값을 0으로
 * 채우지 않고 그 점의 증감을 결측으로 남긴다. 창의 첫 점은 비교할 이전 값이 없어 항상
 * 결측이다.
 */
export function deltaSeriesOf(
  series: ChartSeries[],
  maxGapDays: number = MAX_GAP_DAYS,
): ChartSeries[] {
  return series.map((s) => {
    const out: TimePoint[] = []
    let prev: TimePoint | null = null
    for (const p of s.points) {
      if (p.v === null) {
        out.push({ t: p.t, v: null })
        prev = null
        continue
      }
      if (prev === null || broken(prev, p, maxGapDays)) {
        out.push({ t: p.t, v: null })
      } else {
        out.push({ t: p.t, v: p.v - (prev.v as number) })
      }
      prev = p
    }
    return { ...s, points: out }
  })
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
