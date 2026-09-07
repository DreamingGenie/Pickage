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
  evidenceId?: string
}

export const FEATURE_ROWS: { label: string; cells: FeatureCell[] }[] = [
  {
    label: 'Node 최소 버전 선언',
    cells: [
      { verdict: 'SUPPORTED', note: '>=12', evidenceId: 'ev-engines-winston' },
      { verdict: 'UNCONFIRMED', evidenceId: 'ev-engines-pino' },
      {
        verdict: 'CONDITIONALLY_SUPPORTED',
        note: '비표준 >=0.10',
        evidenceId: 'ev-engines-bunyan',
      },
    ],
  },
  {
    label: '번들 타입 선언',
    cells: [
      {
        verdict: 'CONDITIONALLY_SUPPORTED',
        note: 'named export 경고',
        evidenceId: 'ev-types-winston',
      },
      { verdict: 'SUPPORTED', evidenceId: 'ev-types-pino' },
      { verdict: 'UNSUPPORTED', note: '번들 타입 없음', evidenceId: 'ev-types-bunyan' },
    ],
  },
  {
    label: 'provenance',
    cells: [
      { verdict: 'UNCONFIRMED', evidenceId: 'ev-prov-winston' },
      { verdict: 'SUPPORTED', evidenceId: 'ev-prov-pino' },
      { verdict: 'UNCONFIRMED', evidenceId: 'ev-prov-bunyan' },
    ],
  },
]

export interface EvidenceRecord {
  title: string
  /** 표시 문자열. 클릭 가능한 URL 을 내려보내지 않는다(IA 1.12 · 구상안 10). */
  source: string
  excerpt: string
  collectedAt: string
}

export const EVIDENCE: Record<string, EvidenceRecord> = {
  'ev-engines-winston': {
    title: 'winston 3.19.0 engines 선언',
    source: 'TARBALL_PACKAGE_JSON · package.json > engines',
    excerpt: '"engines": { "node": ">= 12.0.0" }',
    collectedAt: '2026-08-31',
  },
  'ev-engines-pino': {
    title: 'pino 10.3.1 engines 선언 확인 범위',
    source: 'SEARCH_TRACE · package.json · README',
    excerpt:
      'package.json 에 engines 항목이 없고 README 에서도 최소 Node 버전 언급을 찾지 못했습니다. 지원하지 않는다는 뜻이 아니라 이 버전 자료에서 확인되지 않았다는 뜻입니다.',
    collectedAt: '2026-08-31',
  },
  'ev-engines-bunyan': {
    title: 'bunyan 1.8.15 비표준 engine 선언',
    source: 'TARBALL_PACKAGE_JSON · package.json > engines',
    excerpt:
      '"engines": { "node": ">=0.10" } — semver 범위로는 해석되나 현행 Node 를 반영하지 않습니다.',
    collectedAt: '2026-08-31',
  },
  'ev-types-winston': {
    title: 'winston 3.19.0 타입 진입 경고',
    source: 'STATIC_ANALYZER · Are The Types Wrong',
    excerpt: 'CommonJS 배포본에서 ESM named import 시 경고가 보고되었습니다.',
    collectedAt: '2026-08-31',
  },
  'ev-types-pino': {
    title: 'pino 10.3.1 타입 진입 검사',
    source: 'STATIC_ANALYZER · Are The Types Wrong',
    excerpt: '정적 타입 진입 검사에서 보고된 문제가 없습니다.',
    collectedAt: '2026-08-31',
  },
  'ev-types-bunyan': {
    title: 'bunyan 1.8.15 번들 타입 없음',
    source: 'TARBALL_PACKAGE_JSON · types · typings 필드 부재',
    excerpt: '배포본에 타입 선언이 동봉되어 있지 않습니다.',
    collectedAt: '2026-08-31',
  },
  'ev-prov-winston': {
    title: 'winston 3.19.0 provenance 확인 범위',
    source: 'SEARCH_TRACE · Registry · deps.dev',
    excerpt: '현재 자료에서 provenance 를 확인하지 못했습니다.',
    collectedAt: '2026-08-31',
  },
  'ev-prov-pino': {
    title: 'pino 10.3.1 provenance',
    source: 'REGISTRY_METADATA · deps.dev',
    excerpt: 'provenance 가 확인되었습니다.',
    collectedAt: '2026-08-31',
  },
  'ev-prov-bunyan': {
    title: 'bunyan 1.8.15 provenance 확인 범위',
    source: 'SEARCH_TRACE · Registry · deps.dev',
    excerpt: '현재 자료에서 provenance 를 확인하지 못했습니다.',
    collectedAt: '2026-08-31',
  },
}
