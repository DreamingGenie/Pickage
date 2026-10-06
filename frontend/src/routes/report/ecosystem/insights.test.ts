import { describe, expect, it } from 'vitest'

import { downloadTierOf, trendOf } from '@/routes/report/ecosystem/insights'

/** 매주 월요일 점을 `values` 만큼 만든다. */
function weekly(values: number[]) {
  const start = Date.parse('2026-01-05T00:00:00Z')
  return {
    key: 'p',
    label: 'p',
    points: values.map((v, i) => ({
      t: new Date(start + i * 7 * 86_400_000).toISOString().slice(0, 10),
      v,
    })),
  }
}

describe('downloadTierOf', () => {
  it('고정 구간으로 나눈다 — 비교 대상끼리 순위를 매기지 않는다', () => {
    expect(downloadTierOf(null)).toBeNull()
    expect(downloadTierOf(2_000_000)).toBe('high')
    expect(downloadTierOf(50_000)).toBe('mid')
    expect(downloadTierOf(900)).toBe('low')
  })
})

describe('trendOf', () => {
  it('3개월 전보다 10% 넘게 오르면 증가, 내리면 감소, 그 안이면 유지', () => {
    const flat = Array(14).fill(100)
    expect(trendOf(weekly([...flat.slice(0, 13), 120]))?.direction).toBe('up')
    expect(trendOf(weekly([...flat.slice(0, 13), 85]))?.direction).toBe('down')
    expect(trendOf(weekly([...flat.slice(0, 13), 105]))?.direction).toBe('flat')
  })

  it('3개월 치 자료가 없으면 판단하지 않는다', () => {
    expect(trendOf(weekly([100, 200, 300]))).toBeNull()
  })

  it('시작 값이 0 이면 비율을 낼 수 없어 판단하지 않는다', () => {
    expect(trendOf(weekly([...Array(13).fill(0), 50]))).toBeNull()
  })
})
