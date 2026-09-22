import { describe, expect, it } from 'vitest'

import type { RagComparisonResult } from '@/api/types'
import { diffAnalyses, isEmptyChange } from '@/routes/report/features/adapter'
import { toComparisonView, toFeaturesPdfPayload } from '@/routes/report/features/rag-adapter'

/** 화면 모델 변환 — 공통점·패키지별 차이점 서술 (2026-09-22). */
function result(over: Partial<RagComparisonResult> = {}): RagComparisonResult {
  const packages = [
    { package: 'pino', version: '10.3.1' },
    { package: 'winston', version: '3.19.0' },
  ]
  return {
    dataStatus: 'COMPLETE',
    packages,
    common: '둘 다 로그를 남겨요.',
    differences: packages.map((p) => ({ ...p, body: `${p.package} 설명` })),
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
  it('공통점과 패키지별 차이점을 화면 모델로 옮긴다', () => {
    const view = toComparisonView(result())

    expect(view.packages).toEqual([
      { name: 'pino', version: '10.3.1' },
      { name: 'winston', version: '3.19.0' },
    ])
    expect(view.common).toBe('둘 다 로그를 남겨요.')
    expect(view.differences.map((d) => d.body)).toEqual(['pino 설명', 'winston 설명'])
    expect(view.limited).toBe(false)
  })

  it('차이점은 요청한 패키지 순서로 세우고, 빠진 패키지는 빈 문단으로 둔다', () => {
    const view = toComparisonView(
      result({ differences: [{ package: 'winston', version: '3.19.0', body: 'w' }] }),
    )

    expect(view.differences).toEqual([
      { name: 'pino', version: '10.3.1', body: '' },
      { name: 'winston', version: '3.19.0', body: 'w' },
    ])
  })

  it('RAG 가 자료가 부족하다고 하면 그대로 적는다', () => {
    expect(toComparisonView(result({ dataStatus: 'COMPARISON_LIMITED' })).limited).toBe(true)
  })
})

describe('toFeaturesPdfPayload', () => {
  it('백엔드 계약(snake_case)으로 옮긴다', () => {
    expect(toFeaturesPdfPayload(result())).toEqual({
      packages: [
        { package_name: 'pino', version: '10.3.1' },
        { package_name: 'winston', version: '3.19.0' },
      ],
      common: '둘 다 로그를 남겨요.',
      differences: [
        { package_name: 'pino', version: '10.3.1', body: 'pino 설명' },
        { package_name: 'winston', version: '3.19.0', body: 'winston 설명' },
      ],
      limited: false,
    })
  })
})

describe('diffAnalyses', () => {
  it('버전 변화를 잡는다', () => {
    const prev = toComparisonView(result())
    const next = toComparisonView(
      result({
        packages: [
          { package: 'pino', version: '10.2.0' },
          { package: 'winston', version: '3.19.0' },
        ],
      }),
    )

    const change = diffAnalyses(prev, next)

    expect(change.versionChanges).toEqual([{ name: 'pino', from: '10.3.1', to: '10.2.0' }])
    expect(isEmptyChange(change)).toBe(false)
  })

  it('같은 버전을 다시 받으면 문장이 달라도 변경점이 없다', () => {
    const view = toComparisonView(result())
    const again = toComparisonView(result({ common: '다른 문장이에요.' }))

    expect(isEmptyChange(diffAnalyses(view, again))).toBe(true)
  })
})
