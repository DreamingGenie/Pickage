/**
 * 시리즈 구분값.
 *
 * 규칙(임의로 정하지 않는다):
 *   0번 = 기준 패키지 → 실선
 *   1번 이후 = 사용자가 고른 순서대로 → 긴 파선, 점선
 * 즉 선 모양은 **최종 비교 순서**(IA 11.1)를 그대로 따르며, 카드·범례·차트에서
 * 같은 순서를 쓰기 때문에 세 곳의 표기가 어긋나지 않는다.
 *
 * 파선을 쓰는 이유는 IA 1.11 — 색상만으로 의미를 전달하지 않는다.
 * 흑백 PDF 로 뽑아도 세 선이 갈라져야 한다.
 */
export interface SeriesStyle {
  color: string
  dash: string | undefined
  /** 스크린리더·범례에서 색 대신 읽어줄 이름 */
  patternLabel: string
}

export const SERIES_STYLES: SeriesStyle[] = [
  { color: '#0F172A', dash: undefined, patternLabel: '실선' },
  { color: '#0E7C6B', dash: '7 3', patternLabel: '긴 파선' },
  { color: '#9A6A00', dash: '2 3', patternLabel: '점선' },
]

export const seriesStyle = (i: number): SeriesStyle => SERIES_STYLES[i % SERIES_STYLES.length]

/**
 * 교체 흐름 막대의 도착지 색 — **다섯 단계.**
 *
 * `SHARE_FILLS` 를 쓰지 않는 이유는 그쪽이 네 칸이라 다섯째 도착지에서 색이 처음으로
 * 되돌아가기 때문이다. 막대만 보면 같은 색 조각이 둘이라 하나로 읽힌다 — 범례에 비율이
 * 있어도 막대의 모양이 먼저 눈에 들어온다. 도착지는 최대 다섯 개다(API 가 상위 5만 준다).
 */
export const FLOW_FILLS = ['#0F172A', '#334155', '#64748B', '#94A3B8', '#CBD5E1']

/** Version Share 계열 색. UNRESOLVED 는 색이 아니라 빗금으로 구분한다. */
export const SHARE_FILLS = ['#0F172A', '#475569', '#94A3B8', '#CBD5E1']
export const UNRESOLVED_FILL = 'url(#pk-hatch)'
