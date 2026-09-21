/**
 * 기능 비교 예시.
 *
 * 구상안 16장 POC 실측 결과를 그대로 옮겼다. 지어낸 값이 아니라
 * winston 3.19.0 · pino 10.3.1 · bunyan 1.8.15 에서 실제로 확인된 것만 담는다.
 *
 * UNSUPPORTED 는 공식 부정 근거가 연결된 경우에만 쓴다(구상안 7.2).
 * 자료에서 확인되지 않은 것은 UNCONFIRMED 이며, 판정 실패가 아니라 확인 범위 표시다.
 */

export type Verdict =
  'SUPPORTED' | 'CONDITIONALLY_SUPPORTED' | 'LIMITED_SUPPORT' | 'UNCONFIRMED' | 'UNSUPPORTED'

/** 화면 표기는 IA 9.2 를 따른다. */
export const VERDICT_LABEL: Record<Verdict, string> = {
  SUPPORTED: '지원',
  CONDITIONALLY_SUPPORTED: '조건부',
  LIMITED_SUPPORT: '제한적',
  UNCONFIRMED: '미확인',
  UNSUPPORTED: '미지원',
}

export const COMPARISON_PACKAGES = ['winston@3.19.0', 'pino@10.3.1', 'bunyan@1.8.15'] as const

export interface FeatureCell {
  verdict: Verdict
  note?: string
}

export const FEATURE_ROWS: { label: string; cells: FeatureCell[] }[] = [
  {
    label: 'Node 최소 버전 선언',
    cells: [
      { verdict: 'SUPPORTED', note: '>=12' },
      { verdict: 'UNCONFIRMED' },
      {
        verdict: 'CONDITIONALLY_SUPPORTED',
        note: '비표준 >=0.10',
      },
    ],
  },
  {
    label: '번들 타입 선언',
    cells: [
      {
        verdict: 'CONDITIONALLY_SUPPORTED',
        note: 'named export 경고',
      },
      { verdict: 'SUPPORTED' },
      { verdict: 'UNSUPPORTED', note: '번들 타입 없음' },
    ],
  },
  {
    label: 'provenance',
    cells: [{ verdict: 'UNCONFIRMED' }, { verdict: 'SUPPORTED' }, { verdict: 'UNCONFIRMED' }],
  },
]
