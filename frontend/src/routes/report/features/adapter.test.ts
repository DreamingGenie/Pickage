import { describe, expect, it } from 'vitest'

import type { RagComparisonResult } from '@/api/types'
import { diffAnalyses, isEmptyChange } from '@/routes/report/features/adapter'
import {
  cellReason,
  evidenceLabel,
  sourceLabel,
  sourcePackage,
} from '@/routes/report/features/model'
import { toComparisonView } from '@/routes/report/features/rag-adapter'

/**
 * 화면 모델 변환 (S15P21A506-217 · BE-130).
 *
 * <h2>왜 RAG 응답으로 시험하나</h2>
 *
 * 판정표의 출처가 `POST /packages/feature-comparison` 하나로 정리됐다. 옛 POC 응답
 * (`adaptComparison`)은 지웠으므로, 변경점 계산도 지금 실제로 들어오는 모양으로 확인한다.
 */
function result(over: Partial<RagComparisonResult> = {}): RagComparisonResult {
  const packages = [
    { package: 'pino', version: '10.3.1' },
    { package: 'winston', version: '3.19.0' },
  ]
  return {
    dataStatus: 'COMPLETE',
    packages,
    features: [1, 2, 3, 4, 5].map((n) => ({
      featureLabel: `기능 ${n}`,
      results: packages.map((p, i) => ({
        package: p.package,
        version: p.version,
        verdict: 'SUPPORTED' as const,
        evidenceIds: [`E${n}${i}`],
        groundedIn: 'EVIDENCE' as const,
        note: null,
      })),
    })),
    narrative: [],
    narrativeError: null,
    sources: packages.map((p) => ({
      package: p.package,
      version: p.version,
      status: 'OK' as const,
      readmeBytes: 4096,
      proseChars: 2048,
    })),
    ...over,
  }
}

describe('toComparisonView', () => {
  it('camelCase 응답을 화면 모델로 옮기고 근거 수를 중복 없이 센다', () => {
    const view = toComparisonView(result())

    expect(view.packages).toEqual([
      { name: 'pino', version: '10.3.1' },
      { name: 'winston', version: '3.19.0' },
    ])
    expect(view.rows).toHaveLength(5)
    expect(view.evidenceCount).toBe(10)
    expect(view.limited).toBe(false)
  })

  it('RAG 가 비교 가능한 기능이 부족하다고 하면 그대로 적는다', () => {
    expect(toComparisonView(result({ dataStatus: 'COMPARISON_LIMITED' })).limited).toBe(true)
  })

  /**
   * 근거 없이 답한 셀은 그 사실이 화면에 남아야 한다 — 구상안이 근거 연결을 요구하므로
   * 연결이 없다는 것 자체가 사용자가 알아야 할 정보다.
   */
  it('일반 지식으로 답한 셀은 근거가 비고, 그 사실을 note 에 적는다', () => {
    const one = result()
    one.features[0].results[0] = {
      package: 'pino',
      version: '10.3.1',
      verdict: 'UNCONFIRMED',
      evidenceIds: [],
      groundedIn: 'GENERAL_KNOWLEDGE',
      note: null,
    }

    const cell = toComparisonView(one).rows[0].cells[0]
    expect(cell.evidenceIds).toEqual([])
    expect(cell.note).toBe('확인한 자료가 아니라 일반 지식에 근거함')
  })

  /** 재시도가 없는 파이프라인이라 0 이다 — 화면이 재시도 버튼을 두지 않는 근거. */
  it('재시도 대상 셀을 세지 않는다', () => {
    expect(toComparisonView(result()).retryableCells).toBe(0)
  })
})

describe('diffAnalyses', () => {
  it('버전·판정·근거 변화를 잡는다', () => {
    const prev = toComparisonView(result())

    const next = result({
      packages: [
        { package: 'pino', version: '10.2.0' },
        { package: 'winston', version: '3.19.0' },
      ],
    })
    next.features[0].results[0] = {
      package: 'pino',
      version: '10.2.0',
      verdict: 'LIMITED_SUPPORT',
      evidenceIds: ['E10b'],
      groundedIn: 'EVIDENCE',
      note: null,
    }

    const change = diffAnalyses(prev, toComparisonView(next))

    expect(change.versionChanges).toEqual([{ name: 'pino', from: '10.3.1', to: '10.2.0' }])
    expect(change.verdictChanges).toEqual([
      { feature: '기능 1', name: 'pino', from: 'SUPPORTED', to: 'LIMITED_SUPPORT' },
    ])
    expect(change.evidenceAdded).toBe(1)
    expect(change.evidenceRemoved).toBe(1)
    expect(isEmptyChange(change)).toBe(false)
  })

  it('같은 결과를 다시 받으면 변경점이 없다', () => {
    const view = toComparisonView(result())

    expect(isEmptyChange(diffAnalyses(view, toComparisonView(result())))).toBe(true)
  })
})

describe('셀 표기', () => {
  const base = toComparisonView(result()).rows[0].cells[0]

  /** RAG 의 ID 는 기계용이라 그대로 적으면 읽을 수 없다. README 의 어디인지만 말한다. */
  it('근거 ID 를 읽히는 출처 이름으로 바꾸고, 여럿이면 개수로 줄인다', () => {
    const at = (ids: string[]) => evidenceLabel({ ...base, evidenceIds: ids })

    expect(at(['pino@10.3.1#0'])).toBe('README 1번째 단락')
    expect(at(['pino@10.3.1#meta-desc'])).toBe('패키지 소개')
    expect(at(['@babel/core@7.28.4#meta-entry'])).toBe('불러오는 방식')
    expect(at(['pino@10.3.1#3', 'pino@10.3.1#4', 'pino@10.3.1#9'])).toBe('README 4번째 단락 외 2곳')
    expect(at([])).toBeNull()
  })

  it('스코프 패키지의 출처에서도 패키지 이름을 바르게 떼어 낸다', () => {
    expect(sourcePackage('@babel/core@7.28.4#2')).toBe('@babel/core')
    expect(sourcePackage('pino@10.3.1#meta-desc')).toBe('pino')
    expect(sourceLabel('E10')).toBe('원문')
  })

  it('미확인 사유는 글자로 말하고, 사유가 없으면 적지 않는다', () => {
    expect(cellReason(base)).toBeNull()
    expect(cellReason({ ...base, reasonCode: 'SOURCE_ABSENT' })).toBe(
      '확인한 자료에서 발견되지 않음',
    )
    expect(cellReason({ ...base, dataStatus: 'CONFLICT' })).toBe('같은 버전 근거가 충돌')
  })
})
