import { describe, expect, it } from 'vitest'

import type { FeatureCellWire, FeatureComparisonResponse } from '@/api/types'
import {
  adaptComparison,
  adaptVersions,
  diffAnalyses,
  isEmptyChange,
} from '@/routes/report/features/adapter'
import { cellReason, evidenceLabel } from '@/routes/report/features/model'

function cell(
  name: string,
  version: string,
  verdict: FeatureCellWire['verdict'],
  extra: Partial<FeatureCellWire> = {},
): FeatureCellWire {
  return {
    package_name: name,
    version,
    verdict,
    data_status: 'COMPLETE',
    evidence_ids: [],
    note: null,
    reason_code: null,
    ...extra,
  }
}

function response(over: Partial<FeatureComparisonResponse> = {}): FeatureComparisonResponse {
  return {
    data_status: 'COMPLETE',
    comparison_state: 'COMPLETE',
    packages: [
      { package_name: 'pino', version: '10.3.1' },
      { package_name: 'winston', version: '3.19.0' },
    ],
    environment: null,
    environment_note: null,
    features: [1, 2, 3, 4, 5].map((n) => ({
      feature_id: `f${n}`,
      feature_label: `기능 ${n}`,
      results: [
        cell('pino', '10.3.1', 'SUPPORTED', { evidence_ids: [`E${n}0`] }),
        cell('winston', '3.19.0', 'SUPPORTED', { evidence_ids: [`E${n}1`] }),
      ],
    })),
    narrative: [],
    narrative_error: null,
    evidence_count: null,
    analyzed_at: '2026-09-02T09:24:00+09:00',
    ...over,
  }
}

describe('adaptComparison', () => {
  it('snake_case 응답을 화면 모델로 바꾸고 근거 수를 중복 없이 센다', () => {
    const view = adaptComparison(response())

    expect(view.packages).toEqual([
      { name: 'pino', version: '10.3.1' },
      { name: 'winston', version: '3.19.0' },
    ])
    expect(view.rows[0].cells[0]).toMatchObject({
      packageName: 'pino',
      verdict: 'SUPPORTED',
      evidenceIds: ['E10'],
    })
    expect(view.evidenceCount).toBe(10)
    expect(view.isExample).toBe(false)
  })

  it('서버가 근거 수를 주면 그 값을 쓴다', () => {
    expect(adaptComparison(response({ evidence_count: 18 })).evidenceCount).toBe(18)
  })

  it('환경 표의 값을 packages 순서로 다시 세우고 없는 값은 null 로 둔다', () => {
    const view = adaptComparison(
      response({
        environment: [
          {
            key: 'node',
            label: 'Node.js',
            // 응답의 값 순서가 packages 와 반대여도 열은 packages 를 따른다
            values: [
              { package_name: 'winston', value: null },
              { package_name: 'pino', value: '>=12' },
            ],
          },
        ],
      }),
    )

    expect(view.environment).toEqual([{ key: 'node', label: 'Node.js', values: ['>=12', null] }])
  })

  it('환경 표가 없으면 빈 배열이다 — 섹션을 그리지 않는다', () => {
    expect(adaptComparison(response({ environment: null })).environment).toEqual([])
  })

  it('기능이 5개 미만이거나 서버가 제한을 알리면 limited 다', () => {
    expect(adaptComparison(response()).limited).toBe(false)

    const fewer = response()
    fewer.features = fewer.features.slice(0, 2)
    expect(adaptComparison(fewer).limited).toBe(true)

    expect(adaptComparison(response({ comparison_state: 'COMPARISON_LIMITED' })).limited).toBe(true)
  })

  it('다시 시도하면 나아질 사유의 셀만 재시도 대상으로 센다', () => {
    const r = response()
    r.features[0].results[0] = cell('pino', '10.3.1', 'UNCONFIRMED', {
      reason_code: 'TRANSIENT_FETCH_ERROR',
    })
    r.features[1].results[0] = cell('pino', '10.3.1', 'UNCONFIRMED', {
      reason_code: 'SOURCE_ABSENT',
    })
    r.features[2].results[0] = cell('pino', '10.3.1', 'UNCONFIRMED', {
      reason_code: 'EVIDENCE_CONFLICT',
    })

    expect(adaptComparison(r).retryableCells).toBe(1)
  })
})

describe('adaptVersions', () => {
  it('정식 버전이 없으면 latestStable 이 null 이다', () => {
    const [pkg] = adaptVersions({
      packages: [
        {
          package_name: 'left-pad',
          latest_stable: null,
          versions: [{ version: '1.4.0-beta.1', prerelease: true }],
        },
      ],
    })

    expect(pkg).toEqual({
      name: 'left-pad',
      latestStable: null,
      choices: [{ version: '1.4.0-beta.1', prerelease: true }],
    })
  })
})

describe('diffAnalyses', () => {
  it('버전·판정·근거 변화를 잡는다', () => {
    const prev = adaptComparison(response())

    const next = response({
      packages: [
        { package_name: 'pino', version: '10.2.0' },
        { package_name: 'winston', version: '3.19.0' },
      ],
    })
    next.features[0].results[0] = cell('pino', '10.2.0', 'LIMITED_SUPPORT', {
      evidence_ids: ['E10b'],
    })
    next.features[1].results[0] = cell('pino', '10.2.0', 'SUPPORTED', { evidence_ids: ['E20'] })

    const change = diffAnalyses(prev, adaptComparison(next))

    expect(change.versionChanges).toEqual([{ name: 'pino', from: '10.3.1', to: '10.2.0' }])
    expect(change.verdictChanges).toEqual([
      { feature: '기능 1', name: 'pino', from: 'SUPPORTED', to: 'LIMITED_SUPPORT' },
    ])
    expect(change.evidenceAdded).toBe(1)
    expect(change.evidenceRemoved).toBe(1)
    expect(isEmptyChange(change)).toBe(false)
  })

  it('같은 결과를 다시 받으면 변경점이 없다', () => {
    const view = adaptComparison(response())

    expect(isEmptyChange(diffAnalyses(view, adaptComparison(response())))).toBe(true)
  })
})

describe('셀 표기', () => {
  const base = adaptComparison(response()).rows[0].cells[0]

  it('E 번호 근거는 패키지·버전과 함께 적고 그 밖의 형식은 그대로 둔다', () => {
    expect(evidenceLabel(base)).toBe('pino@10.3.1 · E10')
    expect(evidenceLabel({ ...base, evidenceIds: ['ev-engines-pino'] })).toBe('ev-engines-pino')
    expect(evidenceLabel({ ...base, evidenceIds: [] })).toBeNull()
  })

  it('미확인 사유는 글자로 말하고, 사유가 없으면 적지 않는다', () => {
    expect(cellReason(base)).toBeNull()
    expect(cellReason({ ...base, reasonCode: 'SOURCE_ABSENT' })).toBe(
      '확인한 자료에서 발견되지 않음',
    )
    expect(cellReason({ ...base, dataStatus: 'CONFLICT' })).toBe('같은 버전 근거가 충돌')
  })
})
