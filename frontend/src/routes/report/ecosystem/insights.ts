import type { ChartSeries } from '@/components/charts/geometry'

/**
 * 패키지 카드의 한마디 판단 — 다운로드 수준과 3개월 추세.
 *
 * **비교 대상끼리 순위를 매기지 않는다**(IA 1-12). 다운로드 수준은 고정 구간으로, 추세는 그 패키지
 * 자신의 3개월 전과 비교한다. 그래서 셋이 모두 "높은 편" 이거나 모두 "감소" 일 수 있다.
 */

/* ── 다운로드 수준 ──────────────────────────────────────────────────── */

export type DownloadTier = 'high' | 'mid' | 'low'

/**
 * 주간 다운로드 구간. 서비스가 다루는 인기 상위 패키지 모집단을 기준으로 잡은 값이다.
 * 값이 바뀌면 여기만 고친다 — 실제 분포(백분위)를 보고 조정할 수 있다.
 */
export const DOWNLOAD_TIER_BOUNDS = { high: 1_000_000, low: 10_000 } as const

export const DOWNLOAD_TIER_LABEL: Record<DownloadTier, string> = {
  high: '높은 편',
  mid: '평범한 편',
  low: '낮은 편',
}

export function downloadTierOf(weekly: number | null): DownloadTier | null {
  if (weekly === null) return null
  if (weekly >= DOWNLOAD_TIER_BOUNDS.high) return 'high'
  if (weekly < DOWNLOAD_TIER_BOUNDS.low) return 'low'
  return 'mid'
}

/* ── 3개월 추세 ─────────────────────────────────────────────────────── */

export type TrendDirection = 'up' | 'flat' | 'down'

export interface Trend {
  direction: TrendDirection
  /** 증감 비율. 0.12 = 12% 증가 */
  rate: number
}

export const TREND_LABEL: Record<TrendDirection, string> = {
  up: '증가',
  flat: '유지',
  down: '감소',
}

/** 비교 거리 — 3개월(13주). */
const TREND_WEEKS = 13
/** 이만큼 넘게 움직여야 증가·감소로 본다. 그 안은 유지. */
const TREND_THRESHOLD = 0.1
const DAY = 24 * 60 * 60 * 1000

/**
 * 최근 값과 3개월 전 값을 비교해 증감 비율을 낸다.
 *
 * `smooth` 주 만큼 평균을 내서 양 끝을 잡는다 — 다운로드는 주마다 크게 출렁여서 한 주 값끼리
 * 비교하면 우연히 튄 주가 결론을 뒤집는다. 의존 등록 수는 쌓이는 값이라 1주면 된다.
 *
 * 3개월 전 자료가 없거나(모으기 시작한 지 얼마 안 됨) 시작 값이 0 이면 판단하지 않는다(null).
 */
export function trendOf(series: ChartSeries | undefined, smooth = 1): Trend | null {
  const points = (series?.points ?? []).filter((p): p is { t: string; v: number } => p.v !== null)
  if (points.length < 2) return null

  const lastT = Date.parse(points[points.length - 1].t)
  const pivot = lastT - TREND_WEEKS * 7 * DAY
  // 3개월 전 시점에 가장 가까운(그 이전의) 관측
  let startIdx = -1
  for (let i = points.length - 1; i >= 0; i--) {
    if (Date.parse(points[i].t) <= pivot) {
      startIdx = i
      break
    }
  }
  if (startIdx < 0) return null

  const avg = (from: number, to: number) => {
    const slice = points.slice(Math.max(0, from), to + 1)
    return slice.reduce((sum, p) => sum + p.v, 0) / slice.length
  }
  const end = avg(points.length - smooth, points.length - 1)
  const start = avg(startIdx - smooth + 1, startIdx)
  if (start <= 0) return null

  const rate = (end - start) / start
  const direction: TrendDirection =
    rate > TREND_THRESHOLD ? 'up' : rate < -TREND_THRESHOLD ? 'down' : 'flat'
  return { direction, rate }
}

/** 다운로드는 4주 평균, 의존 등록 수는 한 주 값으로 비교한다. */
export const DOWNLOADS_SMOOTH_WEEKS = 4
