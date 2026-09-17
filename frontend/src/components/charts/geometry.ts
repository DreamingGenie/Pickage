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

/** `niceMax` 의 부호 있는 버전. 증감 축의 아래쪽(음수) 여유를 같은 규칙으로 올린다. */
function niceBound(v: number): number {
  if (v === 0) return 0
  return v < 0 ? -niceMax(-v) : niceMax(v)
}

/**
 * 지수(=100 기준) 비교 축의 도메인. **0 을 강제하지 않는다** — 이 축의 기준선은 100 이지
 * 0 이 아니다(변화 없음 = 100). 그래서 `extentY` 의 "잘린 축은 과장한다" 경고가 여기엔
 * 적용되지 않는다: 100 언저리로 좁혀 그리는 것이 이 그래프의 정의 자체다.
 *
 * 100 은 항상 도메인에 포함한다 — 기준선이 화면 밖으로 나가면 "무엇 대비 몇 %"인지
 * 읽을 수 없다. 데이터가 100 근처에 몰려 있어도 위아래로 최소 여유를 둔다(2p, 그리고
 * 실제 편차의 12%) — 값이 전부 정확히 100(첫 관측치 자기 자신)인 첫 스냅샷 부근에서
 * 도메인이 [100,100] 으로 붕괴해 선이 찌그러지는 것을 막는다.
 */
export function indexedExtentY(series: ChartSeries[]): Domain {
  let lo = Infinity
  let hi = -Infinity
  for (const s of series) {
    for (const p of s.points) {
      if (p.v === null) continue
      if (p.v < lo) lo = p.v
      if (p.v > hi) hi = p.v
    }
  }
  if (!Number.isFinite(lo)) return [90, 110]
  lo = Math.min(lo, 100)
  hi = Math.max(hi, 100)
  const pad = Math.max((hi - lo) * 0.12, 2)
  return [lo - pad, hi + pad]
}

/**
 * 증감(전 스냅샷 대비 순증감) 그래프의 도메인. **0 은 항상 포함한다** — 여기서 0 은 절대값
 * 축과 달리 임의의 바닥이 아니라 "변화 없음"이라는 실제 기준선이라, 포함해도 `extentY` 의
 * 과장 문제가 생기지 않는다. 위아래 모두 `niceMax` 로 올려 음수 구간도 대칭적으로 여유를
 * 둔다.
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
 * y축은 로그 공간에서 그린다(311a). 의존 수·다운로드 모두 몇 자릿수를 오가서, 선형 축이면
 * 큰 시리즈 옆에서 작은 시리즈가 바닥에 눌려 붙는다. `log1p`를 쓰는 이유는 0을 포함하는
 * 도메인(`extentY`가 항상 0을 하한으로 둔다)에서 `log(0)`이 `-Infinity`가 되는 것을 피하기
 * 위해서다 — `log1p(0) = 0`이라 0이 항상 바닥에 안전하게 찍힌다.
 *
 * **이 로그축은 "자릿수가 다른 시리즈"를 위한 것이지 "자릿수는 같은데 몇 % 차이"를 위한
 * 것이 아니다.** 후자는 0~최댓값의 로그 구간 전체 중 실제 데이터가 사는 곳이 맨 위 얇은
 * 띠 하나뿐이라 로그를 써도 안 써도 똑같이 붙어 보인다. 그 경우를 위한 것이 아래
 * `indexedExtentY`/`scaleYLinear`(지수 비교)와 `deltaExtentY`(증감)다 — **축을 0 밖에서
 * 임의로 잘라 확대하는 방식은 쓰지 않는다.** 잘린 절대값 축은 실제로는 작은 차이를 크게
 * 보이게 과장하고, 지수·증감은 "0을 뺀 것"이 아니라 애초에 기준이 다른(100·변화없음)
 * 정직한 지표다.
 */
const toLog = (v: number) => Math.log1p(Math.max(0, v))

export function ticksY([lo, hi]: Domain, count = 3): number[] {
  const lLo = toLog(lo)
  const lHi = toLog(hi)
  const out: number[] = []
  for (let i = 0; i <= count; i++) out.push(Math.expm1(lLo + ((lHi - lLo) * i) / count))
  return out
}

/** 지수·증감처럼 선형 공간이 맞는 축의 눈금. 로그 변환을 거치지 않는다. */
export function ticksYLinear([lo, hi]: Domain, count = 3): number[] {
  const out: number[] = []
  for (let i = 0; i <= count; i++) out.push(lo + ((hi - lo) * i) / count)
  return out
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
 * 로그 없이 그대로 선형 보간한다. 지수(=100 기준) 비교·증감 그래프에 쓴다 — 둘 다 음수가
 * 나올 수 있고(증감) 로그는 음수를 정의하지 못하며, 지수는 애초에 자릿수 차이를 다룰
 * 이유가 없다(기준이 100 하나뿐이라 시리즈 간 규모차가 존재하지 않는다).
 */
export const scaleYLinear = (v: number, d: Domain, b: Box) =>
  d[1] === d[0] ? b.y + b.h : b.y + b.h - ((v - d[0]) / (d[1] - d[0])) * b.h

/**
 * 절대값(0-포함) 로그축의 "낭비 구간" 을 줄인다(379 후속).
 *
 * 원인: 실제로 비교하는 패키지들은 거의 항상 수십만~수천만대인데, 0-포함 로그축은
 * 1~10~100~... 전 자릿수에 똑같은 화면 높이를 나눠 준다. 그 자릿수들에는 데이터가 한 번도
 * 안 닿으니 차트 대부분이 빈 공간이 된다.
 *
 * **그래도 0 을 빼거나 값을 왜곡하지 않는다** — `extentY` 의 "잘린 축은 과장한다" 원칙은
 * 그대로다. 대신 [0, floor] 구간에는 화면 높이의 일부(`BREAK_BAND_FRAC`)만 선형으로 눌러
 * 배정하고, 실제 데이터가 사는 [floor, 최댓값] 구간에 나머지 높이를 로그로 배정한다.
 *
 * **floor 는 비교 중인 두 시리즈의 최솟값이 아니라 도메인 자체의 최댓값에서 고정 비율로
 * 정한다.** 어느 두 패키지를 비교하든 같은 규칙이 적용되므로, 특정 쌍의 격차를 크게
 * 보이려고 그때그때 고른 값이 아니다 — 그 점이 "공정함"의 조건이다. 압축한 자리는
 * `line-chart.tsx` 가 지그재그 표시로 그대로 드러낸다(`breakMarkY`) — 잘랐다는 사실을
 * 숨기지 않는다.
 */
export const BREAK_BAND_FRAC = 0.07

function logBreakFloor(hi: number): number {
  return hi > 0 ? hi / 500 : 1
}

export const scaleYLogBreak = (v: number, d: Domain, b: Box) => {
  const hi = d[1]
  const floor = logBreakFloor(hi)
  const bandH = b.h * BREAK_BAND_FRAC
  const base = b.y + b.h
  if (v <= floor) {
    return base - (Math.max(v, 0) / floor) * bandH
  }
  const lLo = toLog(floor)
  const lHi = toLog(hi)
  const bodyH = b.h - bandH
  return lHi === lLo ? base - bandH : base - bandH - ((toLog(v) - lLo) / (lHi - lLo)) * bodyH
}

/** `scaleYLogBreak` 과 짝을 이루는 눈금. 0 은 항상 찍고, 나머지는 floor~최댓값을 로그로 나눈다. */
export function ticksYLogBreak([, hi]: Domain, count = 3): number[] {
  const floor = logBreakFloor(hi)
  const lLo = toLog(floor)
  const lHi = toLog(hi)
  const out = [0]
  for (let i = 1; i <= count; i++) out.push(Math.expm1(lLo + ((lHi - lLo) * i) / count))
  return out
}

/** 압축 표시(지그재그)를 그릴 y 좌표 — 선형 0~floor 밴드의 위쪽 경계. */
export function breakMarkY(b: Box): number {
  return b.y + b.h - b.h * BREAK_BAND_FRAC
}

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
 * 창의 첫 유효 관측치를 100으로 두고 나머지를 그 대비 비율로 바꾼다(지수 비교 모드).
 *
 * 기준값이 없거나(전부 결측) 0이면 비율을 만들 수 없다 — 지어내지 않고 그 시리즈는
 * 통째로 결측으로 남긴다. **패키지마다 자기 창의 첫 점을 기준으로 삼는다** — 절대
 * 시작일이 달라도(observedFrom 이 갈리는 시리즈) "그 시점부터 몇 % 변했나"는 비교할 수
 * 있어야 한다.
 */
export function indexSeriesTo100(series: ChartSeries[]): ChartSeries[] {
  return series.map((s) => {
    const base = s.points.find((p) => p.v !== null)?.v ?? null
    if (base === null || base === 0) {
      return { ...s, points: s.points.map((p) => ({ t: p.t, v: null })) }
    }
    return {
      ...s,
      points: s.points.map((p) => ({ t: p.t, v: p.v === null ? null : (p.v / base) * 100 })),
    }
  })
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
