import { describe, expect, it } from 'vitest'

import type { TextMark } from '@/api/types'
import { segmentText } from '@/lib/text-marks'

const TEXT = '악성 버전이 npm에 게시되었다. 재발 방지 조치가 제시되었다.'

const term = (start: number, end: number): TextMark => ({
  start,
  end,
  kind: 'KEY_TERM',
})
const sentence = (start: number, end: number): TextMark => ({
  start,
  end,
  kind: 'KEY_SENTENCE',
})

/** 조각을 이어 붙이면 언제나 원문이어야 한다 — 강조가 글을 바꾸면 안 된다. */
const joined = (text: string, marks: TextMark[]) =>
  segmentText(text, marks)
    .map((s) => s.text)
    .join('')

describe('segmentText', () => {
  it('강조가 없으면 통째로 한 조각이다', () => {
    expect(segmentText(TEXT, [])).toEqual([{ text: TEXT, term: false, sentence: false }])
    expect(segmentText(TEXT, undefined)).toHaveLength(1)
    expect(segmentText(TEXT, null)).toHaveLength(1)
  })

  it('빈 글은 조각이 없다', () => {
    expect(segmentText('', [term(0, 1)])).toEqual([])
  })

  it('핵심어와 핵심 문장을 각각 켠다', () => {
    const start = TEXT.indexOf('재발 방지 조치가 제시되었다.')
    const segments = segmentText(TEXT, [term(0, 5), sentence(start, TEXT.length)])

    expect(segments.map((s) => [s.text, s.term, s.sentence])).toEqual([
      ['악성 버전', true, false],
      ['이 npm에 게시되었다. ', false, false],
      ['재발 방지 조치가 제시되었다.', false, true],
    ])
  })

  it('핵심 문장 안의 핵심어는 둘 다 켜진다', () => {
    const start = TEXT.indexOf('재발')
    const termStart = TEXT.indexOf('방지')
    const marks = [sentence(start, TEXT.length), term(termStart, termStart + 2)]

    const inner = segmentText(TEXT, marks).find((s) => s.text === '방지')

    expect(inner).toMatchObject({ term: true, sentence: true })
    expect(joined(TEXT, marks)).toBe(TEXT)
  })

  it('범위를 벗어난·뒤집힌·정수가 아닌·모르는 종류의 구간은 그 구간만 버린다', () => {
    const marks = [
      term(-1, 3),
      term(3, 3),
      term(5, 2),
      term(0, TEXT.length + 1),
      term(0.5, 3),
      { start: 0, end: 3, kind: 'BOLD' } as unknown as TextMark,
      term(0, 5), // 이것만 유효
    ]

    const segments = segmentText(TEXT, marks)

    expect(segments.filter((s) => s.term).map((s) => s.text)).toEqual(['악성 버전'])
    expect(joined(TEXT, marks)).toBe(TEXT)
  })

  it('공백뿐인 구간은 그리지 않는다', () => {
    const space = TEXT.indexOf(' ')
    expect(segmentText(TEXT, [term(space, space + 1)])).toHaveLength(1)
  })

  it('같은 종류가 겹쳐도 글이 깨지지 않는다', () => {
    const marks = [term(0, 5), term(3, 8), sentence(0, 10), sentence(5, 15)]
    expect(joined(TEXT, marks)).toBe(TEXT)
  })

  it('한글·이모지가 섞여도 오프셋은 JS 문자열 기준이다', () => {
    const text = '가나다 🔥 라마바'
    const start = text.indexOf('라마바')

    const segments = segmentText(text, [term(start, start + 3)])

    expect(segments.find((s) => s.term)?.text).toBe('라마바')
  })
})
