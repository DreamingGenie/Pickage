/**
 * 기능 비교 mock (S15P21A506-217).
 *
 * 값은 와이어프레임(기능 비교 · 상태 · Evidence Drawer, 2026-09)을 옮긴 **개발용 화면 확인
 * 자료**다. 분석 결과가 아니므로 `VITE_USE_MOCK=true` 일 때만 쓰인다. 실제 배포에서 사용자가
 * 보는 예시는 구상안 16장 POC 실측(`api/poc-features.ts`)이다.
 *
 * 난수도 실제 시계도 쓰지 않는다 — 새로고침·테스트에서 항상 같은 결과가 나와야 한다
 * (기존 mock 관례).
 *
 * 개발 중 화면을 확인할 때 쓰는 이름:
 * - `pino` `winston` `bunyan` — 정상 완료. 6행에 근거 충돌 셀(winston)과 미확인 셀이 들어 있다.
 *   기본 버전이 아닌 버전을 고르면 몇 개 셀의 판정이 달라져 재분석 변경점을 볼 수 있다.
 * - `bunyan@1.7.0` — 재분석이 실패한다(이전 결과 유지 확인용)
 * - `express` — 부분 완료. 이 패키지 열이 일시적 조회 실패로 미확인이 된다
 * - `koa` — 비교 가능한 기능 부족(`COMPARISON_LIMITED`, 2행)
 * - `left-pad` — 정식 버전이 없다. 사전 배포 버전만 있어 자동 선택이 일어나지 않는다
 * - 그 외 이름 — 앞 2행만 지원, 나머지는 자료에서 발견되지 않음
 */

import { ApiError } from '@/api/client'
import type {
  FeatureCellWire,
  FeatureComparisonResponse,
  FeatureEnvironmentRowWire,
  FeatureNarrativeWire,
  FeatureRowWire,
  FeatureTarget,
  FeatureVerdict,
  FeatureVersionOption,
  FeatureVersionsResponse,
} from '@/api/types'

const LATENCY_MS = 350
const delay = <T>(value: T): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS))

/** 알려진 패키지의 버전 목록. 첫 항목이 최신 안정 버전이다. */
const KNOWN_VERSIONS: Record<string, string[]> = {
  winston: ['3.19.0', '3.18.3', '3.17.0'],
  pino: ['10.3.1', '10.2.0', '9.14.0'],
  bunyan: ['1.8.15', '1.8.14', '1.7.0'],
}

function versionOptions(name: string): FeatureVersionOption {
  if (name === 'left-pad') {
    return {
      package_name: name,
      latest_stable: null,
      versions: [
        { version: '1.4.0-beta.2', prerelease: true },
        { version: '1.4.0-beta.1', prerelease: true },
      ],
    }
  }
  const versions = KNOWN_VERSIONS[name] ?? ['2.0.0', '1.9.0', '1.8.0']
  return {
    package_name: name,
    latest_stable: versions[0],
    versions: versions.map((version) => ({ version, prerelease: false })),
  }
}

export function mockFeatureVersions(names: readonly string[]): Promise<FeatureVersionsResponse> {
  return delay({ packages: names.map(versionOptions) })
}

/* ------------------------------------------------------------------ *
 * 결과
 * ------------------------------------------------------------------ */

type Spec = [verdict: FeatureVerdict, reason?: FeatureCellWire['reason_code'], note?: string]

/** 행 → 패키지 → 판정. 와이어프레임 「핵심 기능 비교」 + Drawer 상세의 ESM 충돌 사례. */
const FEATURES: { id: string; label: string; by: Record<string, Spec> }[] = [
  {
    id: 'structured-json',
    label: '구조화 JSON',
    by: { pino: ['SUPPORTED'], winston: ['SUPPORTED'], bunyan: ['SUPPORTED'] },
  },
  {
    id: 'child-logger',
    label: 'Child logger',
    by: { pino: ['SUPPORTED'], winston: ['SUPPORTED'], bunyan: ['SUPPORTED'] },
  },
  {
    id: 'multi-output',
    label: '다중 출력 경로',
    by: { pino: ['SUPPORTED'], winston: ['SUPPORTED'], bunyan: ['SUPPORTED'] },
  },
  {
    id: 'exception-rejection',
    label: '예외·거부 처리',
    by: {
      pino: ['SUPPORTED'],
      winston: ['UNCONFIRMED', 'SOURCE_ABSENT'],
      bunyan: ['UNCONFIRMED', 'SOURCE_ABSENT'],
    },
  },
  {
    id: 'data-masking',
    label: '데이터 마스킹',
    by: {
      pino: ['UNCONFIRMED', 'SOURCE_ABSENT'],
      winston: ['CONDITIONALLY_SUPPORTED', null, 'Node.js redact 옵션'],
      bunyan: ['UNCONFIRMED', 'SOURCE_ABSENT'],
    },
  },
  {
    id: 'esm-named-import',
    label: 'ESM named import',
    by: {
      pino: ['SUPPORTED'],
      winston: ['UNCONFIRMED', 'EVIDENCE_CONFLICT'],
      bunyan: ['UNCONFIRMED', 'SOURCE_ABSENT'],
    },
  },
]

/** 알려지지 않은 패키지의 기본 판정. 앞 두 행만 안다. */
const UNKNOWN_SPEC = (rowIndex: number): Spec =>
  rowIndex < 2 ? ['SUPPORTED'] : ['UNCONFIRMED', 'SOURCE_ABSENT']

const ENVIRONMENT: Record<string, Record<string, string | null>> = {
  pino: {
    node: '>=12',
    module: 'CommonJS',
    types: '타입 내장',
    deps: '11개',
    files: '40개 · 274.9 KB',
    license: 'MIT',
  },
  winston: {
    node: null,
    module: 'CommonJS · ESM import 가능',
    types: '타입 내장',
    deps: '11개',
    files: '195개 · 663.5 KB',
    license: 'MIT',
  },
  bunyan: {
    node: '>=0.10 · 비표준 선언',
    module: 'CommonJS',
    types: '내장 타입 없음',
    deps: '0개 · 선택 4개',
    files: '6개 · 201.3 KB',
    license: 'MIT',
  },
}

const ENVIRONMENT_ROWS = [
  { key: 'node', label: 'Node.js' },
  { key: 'module', label: '모듈 진입' },
  { key: 'types', label: 'TypeScript' },
  { key: 'deps', label: '직접 의존성' },
  { key: 'files', label: '배포 파일 · 크기' },
  { key: 'license', label: '라이선스' },
]

const NARRATIVE: FeatureNarrativeWire[] = [
  {
    heading: '공통 기반',
    body: '세 패키지 모두 구조화 JSON, child logger, 여러 출력 경로를 구성할 수 있는 공개 근거가 확인되었습니다. 따라서 이 항목은 우열이 아니라 각 패키지가 어떤 API와 확장 구조로 제공하는지를 보는 기준입니다. 이 보고서의 근거 ID는 패키지·버전과 함께 표시됩니다.',
    evidence_ids: ['E01', 'E02', 'E03', 'E04', 'E05', 'E06'],
  },
  {
    heading: '기능 구성 방식의 차이',
    body: 'winston은 transport·format과 예외·거부 처리 API가 함께 드러납니다. pino는 transport·multistream·serializer·formatter·redaction이 구분되어 있으며 브라우저에서는 redaction이 지원되지 않는다고 명시합니다. bunyan은 stream·serializer·rotation·DTrace 관련 기능이 확인됩니다. 각 판정은 해당 패키지·버전 근거 ID로 추적됩니다.',
    evidence_ids: ['E07', 'E10', 'E14'],
  },
  {
    heading: '상황별 확인 기준',
    body: 'ESM named import가 필요하다면 진입 방식 검증이 필요합니다. 브라우저에서도 민감정보 마스킹이 필요하다면 pino의 브라우저 제한을 확인해야 합니다. 번들 타입이 필수라면 bunyan은 별도 타입 의존성을 포함해 검토해야 하며, 내장 rotation이나 DTrace가 요구사항이라면 bunyan의 정확한 동작 범위를 추가로 확인해야 합니다.',
    evidence_ids: ['E13', 'E16', 'E17'],
  },
]

const ENVIRONMENT_NOTE =
  '정적 검사: winston은 ESM named import 주의 · pino는 타입 진입점 문제 없음 · bunyan은 내장 타입 없음'

const pad = (n: number) => String(n).padStart(2, '0')

function isLatest(target: FeatureTarget): boolean {
  return versionOptions(target.package_name).latest_stable === target.version
}

/** 재분석 변경점을 볼 수 있게, 최신이 아닌 버전은 몇 셀의 판정이 다르다. */
function older(name: string, featureId: string, spec: Spec): Spec {
  if (featureId === 'child-logger') return ['LIMITED_SUPPORT', null, `${name} 이전 버전`]
  if (featureId === 'exception-rejection' && spec[0] === 'UNCONFIRMED') {
    return ['SUPPORTED']
  }
  return spec
}

function buildRows(targets: FeatureTarget[], limited: boolean): FeatureRowWire[] {
  const source = limited ? FEATURES.slice(0, 2) : FEATURES
  return source.map((feature, rowIndex) => {
    const results: FeatureCellWire[] = targets.map((target, colIndex) => {
      const name = target.package_name
      let spec = feature.by[name] ?? UNKNOWN_SPEC(rowIndex)
      const latest = isLatest(target)
      if (!latest) spec = older(name, feature.id, spec)

      const [verdict, reason = null, note = null] = spec
      const failing = name === 'express'
      const evidenceNo = rowIndex * 3 + colIndex + 1
      return {
        package_name: name,
        version: target.version,
        verdict: failing ? 'UNCONFIRMED' : verdict,
        data_status: failing
          ? 'COLLECTION_ERROR'
          : reason === 'EVIDENCE_CONFLICT'
            ? 'CONFLICT'
            : verdict === 'UNCONFIRMED'
              ? 'NO_DATA'
              : 'COMPLETE',
        // 최신이 아닌 버전은 근거도 다른 문서에서 나온다 — 변경점에 "근거 추가"가 잡힌다
        evidence_ids: [`E${pad(evidenceNo)}${latest ? '' : 'b'}`],
        note: failing ? null : note,
        reason_code: failing ? 'TRANSIENT_FETCH_ERROR' : reason,
      }
    })
    return { feature_id: feature.id, feature_label: feature.label, results }
  })
}

function buildEnvironment(targets: FeatureTarget[]): FeatureEnvironmentRowWire[] {
  return [
    {
      key: 'version',
      label: '정확한 버전',
      values: targets.map((t) => ({ package_name: t.package_name, value: t.version })),
    },
    ...ENVIRONMENT_ROWS.map((row) => ({
      ...row,
      values: targets.map((t) => ({
        package_name: t.package_name,
        value: ENVIRONMENT[t.package_name]?.[row.key] ?? null,
      })),
    })),
  ]
}

export function mockFeatureComparison(
  targets: FeatureTarget[],
): Promise<FeatureComparisonResponse> {
  const names = targets.map((t) => t.package_name)

  // 재분석 실패 시나리오 — 이전 결과가 화면에 남는지 본다
  if (targets.some((t) => t.package_name === 'bunyan' && t.version === '1.7.0')) {
    return new Promise((_, reject) =>
      setTimeout(
        () => reject(new ApiError(500, 'S001', '분석 서버에서 오류가 발생했습니다.')),
        LATENCY_MS,
      ),
    )
  }

  const limited = names.includes('koa')
  const partial = names.includes('express')
  const rows = buildRows(targets, limited)
  const evidenceCount = rows.reduce(
    (sum, row) => sum + row.results.reduce((s, r) => s + r.evidence_ids.length, 0),
    0,
  )

  return delay({
    data_status: partial ? 'PARTIAL' : 'COMPLETE',
    comparison_state: limited ? 'COMPARISON_LIMITED' : 'COMPLETE',
    packages: targets,
    // 환경 표는 구조화 데이터 계층이 있어야 채워진다. 제한 시나리오에서는 일부러 뺀다.
    environment: limited ? null : buildEnvironment(targets),
    environment_note: limited ? null : ENVIRONMENT_NOTE,
    features: rows,
    narrative: limited ? [] : NARRATIVE,
    narrative_error: null,
    evidence_count: evidenceCount,
    analyzed_at: '2026-09-02T09:24:00+09:00',
  })
}
