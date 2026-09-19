import { describe, expect, it } from 'vitest'

import { PERIOD_PRESETS, resolvePreset, shiftMonths } from '@/routes/report/ecosystem/model'

/** `from`(월요일)부터 `to` 까지 매주 월요일의 ISO 날짜. 실제 집계 달력이 이 모양이다. */
function mondays(from: string, to: string): string[] {
  const out: string[] = []
  const t = new Date(`${from}T00:00:00Z`)
  const end = new Date(`${to}T00:00:00Z`)
  while (t <= end) {
    out.push(t.toISOString().slice(0, 10))
    t.setUTCDate(t.getUTCDate() + 7)
  }
  return out
}

describe('shiftMonths', () => {
  it('개월 수만큼 옮긴다', () => {
    expect(shiftMonths('2026-08-15', -6)).toBe('2026-02-15')
    expect(shiftMonths('2026-01-15', -13)).toBe('2024-12-15')
    expect(shiftMonths('2026-08-15', -36)).toBe('2023-08-15')
  })

  it('도착 달에 그 날이 없으면 그 달 마지막 날로 맞춘다 — 다음 달로 넘어가지 않는다', () => {
    // 2026-08-31 의 6개월 전은 2월 31일이 없다. 3월 3일로 밀리면 반년이 반년이 아니게 된다.
    expect(shiftMonths('2026-08-31', -6)).toBe('2026-02-28')
    expect(shiftMonths('2026-03-31', -1)).toBe('2026-02-28')
    expect(shiftMonths('2024-03-31', -1)).toBe('2024-02-29') // 윤년
  })
})

describe('resolvePreset', () => {
  const snapshots = mondays('2024-01-01', '2026-08-31')
  const last = snapshots[snapshots.length - 1]

  it('프리셋은 다섯 개고 전체 기간이 첫째다', () => {
    expect(PERIOD_PRESETS.map((p) => p.label)).toEqual(['전체 기간', '반년', '1년', '2년', '3년'])
  })

  it('전체 기간은 보유한 처음부터 끝까지다', () => {
    expect(resolvePreset('all', snapshots)).toEqual({ start: snapshots[0], end: last })
  })

  it('끝은 언제나 최신 집계일이고 시작은 끝 − N개월 이후의 첫 집계일이다', () => {
    // 끝 2026-08-31 → 반년 컷오프 2026-02-28 → 그 이후 첫 월요일.
    expect(resolvePreset('6m', snapshots)).toEqual({ start: '2026-03-02', end: '2026-08-31' })
    // 1년 컷오프 2025-08-31(일) → 다음 월요일.
    expect(resolvePreset('1y', snapshots)).toEqual({ start: '2025-09-01', end: '2026-08-31' })
  })

  it('시작·끝은 언제나 받아 둔 집계 날짜다 — 목록에 없는 날짜를 만들지 않는다', () => {
    for (const p of PERIOD_PRESETS) {
      const w = resolvePreset(p.key, snapshots)
      expect(snapshots).toContain(w.start)
      expect(snapshots).toContain(w.end)
    }
  })

  it('자료가 프리셋보다 짧으면 첫 집계일부터다', () => {
    const short = mondays('2026-07-06', '2026-08-31') // 9주
    expect(resolvePreset('3y', short)).toEqual({ start: '2026-07-06', end: '2026-08-31' })
  })

  it('집계가 없으면 빈 구간이다', () => {
    expect(resolvePreset('1y', [])).toEqual({ start: '', end: '' })
  })
})
