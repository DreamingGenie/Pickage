import { describe, expect, it } from 'vitest'

import { ANALYZE_BASE_PARAM, ANALYZE_WITH_PARAM, paths } from '@/app/routes'
import { MAX_PICKED, readAnalyzeSelection } from '@/routes/analyze/analyze-selection'

/** `paths.analyze` 가 만든 주소를 읽는 쪽 입장으로 되돌린다. */
function roundTrip(url: string) {
  const search = new URL(url, 'http://localhost').searchParams
  return readAnalyzeSelection(search.get(ANALYZE_BASE_PARAM), search.get(ANALYZE_WITH_PARAM))
}

describe('readAnalyzeSelection', () => {
  it('기준과 후보를 주소에서 읽는다', () => {
    expect(readAnalyzeSelection('lodash', 'dayjs,luxon')).toEqual({
      base: 'lodash',
      picked: ['dayjs', 'luxon'],
      dropped: [],
      rejected: [],
      acceptedNoSimilar: false,
    })
  })

  it('주소가 비면 빈 1단계다', () => {
    expect(readAnalyzeSelection(null, null)).toEqual({
      base: null,
      picked: [],
      dropped: [],
      rejected: [],
      acceptedNoSimilar: false,
    })
  })

  /*
    S15P21A506-187 이 보고서 화면에서 없앤 실패다. 조용히 자르면 주소에는 더 있는데
    화면에는 상한까지만 뜨고, 무엇이 빠졌는지 알 방법이 없다.
  */
  it('자리를 넘긴 후보는 조용히 사라지지 않고 dropped 로 나온다', () => {
    const selection = readAnalyzeSelection('lodash', 'dayjs,luxon,moment,date-fns')

    expect(selection.picked).toHaveLength(MAX_PICKED)
    expect(selection.picked).toEqual(['dayjs', 'luxon'])
    expect(selection.dropped).toEqual(['moment', 'date-fns'])
  })

  /*
    주소는 사용자가 친 것이 아닐 수 있다. 형식이 아닌 이름을 통과시키면 링크 하나가
    조회 두 건을 버리고 서버에서 V004 만 받아 온다.
  */
  it('npm 이름 형식이 아닌 기준은 조회하지 않고 밝힌다', () => {
    const selection = readAnalyzeSelection('<script>alert(1)</script>', 'dayjs')

    expect(selection.base).toBeNull()
    expect(selection.rejected).toEqual(['<script>alert(1)</script>'])
    expect(selection.picked).toEqual([])
  })

  it('형식이 아닌 후보만 빼고 나머지는 살린다', () => {
    const selection = readAnalyzeSelection('lodash', 'dayjs,NOT VALID')

    expect(selection.picked).toEqual(['dayjs'])
    expect(selection.rejected).toEqual(['NOT VALID'])
  })

  /*
    서버는 중복을 지우고 돌려주므로 조회는 멀쩡하다. 어긋나는 것은 화면이다 —
    선택 칩이 두 번 뜨고 "3개 중 몇 개" 셈이 맞지 않는다.
  */
  it('기준과 같은 이름·중복된 후보는 한 자리만 차지한다', () => {
    const selection = readAnalyzeSelection('lodash', 'lodash,dayjs,dayjs')

    expect(selection.picked).toEqual(['dayjs'])
    expect(selection.dropped).toEqual([])
  })

  it('버전 레인지는 떼고 이름만 조회한다', () => {
    expect(readAnalyzeSelection('lodash@^4', null).base).toBe('lodash')
  })

  it('기준이 없으면 후보는 되살릴 자리가 없어 버린다', () => {
    expect(readAnalyzeSelection(null, 'dayjs,luxon')).toEqual({
      base: null,
      picked: [],
      dropped: [],
      rejected: [],
      acceptedNoSimilar: false,
    })
  })

  it('빈 칸과 공백은 이름으로 세지 않는다', () => {
    expect(readAnalyzeSelection('  lodash  ', ' , dayjs , ')).toMatchObject({
      base: 'lodash',
      picked: ['dayjs'],
    })
  })

  /*
    유사 후보가 없는 기준을 "그래도 쓰겠다" 고 한 확인. 화면 state 로 두면 새로고침 뒤
    기준은 주소에 남는데 화면만 1단계 경고로 되돌아가, 이 화면이 없애려는 실패가 그
    경로에만 남는다.
  */
  it('유사 후보 없음 확인을 주소에서 읽는다', () => {
    expect(readAnalyzeSelection('lodash', null, '1').acceptedNoSimilar).toBe(true)
    expect(readAnalyzeSelection('lodash', null, null).acceptedNoSimilar).toBe(false)
    expect(readAnalyzeSelection('lodash', null, 'true').acceptedNoSimilar).toBe(false)
  })

  /*
    빈 결과가 모듈 상수를 돌려쓰면, 호출부가 그 배열을 제자리에서 한 번만 바꿔도
    이후의 모든 "기준 없음" 결과가 함께 오염된다.
  */
  it('빈 결과도 호출마다 제 배열을 가진다', () => {
    const a = readAnalyzeSelection(null, null)
    const b = readAnalyzeSelection(null, null)

    expect(a.picked).not.toBe(b.picked)
    expect(a.dropped).not.toBe(b.dropped)
  })
})

/*
  주소를 쓰는 쪽과 읽는 쪽이 같은 규칙을 쓰는지 본다. 한쪽만 고쳐지면 "링크는 맞는데
  화면이 비어 있다" 가 되고, 그 어긋남은 두 파일을 나란히 놓기 전에는 보이지 않는다.
*/
describe('paths.analyze ↔ readAnalyzeSelection', () => {
  it('만든 주소를 그대로 되읽는다', () => {
    expect(roundTrip(paths.analyze('lodash', ['dayjs', 'luxon']))).toMatchObject({
      base: 'lodash',
      picked: ['dayjs', 'luxon'],
    })
  })

  it('스코프 이름도 인코딩을 왕복한다', () => {
    expect(roundTrip(paths.analyze('@hapi/hapi', ['express']))).toMatchObject({
      base: '@hapi/hapi',
      picked: ['express'],
    })
  })

  it('기준이 없으면 쿼리를 붙이지 않는다', () => {
    expect(paths.analyze()).toBe('/analyze')
    expect(paths.analyze(null, ['dayjs'])).toBe('/analyze')
  })
})
