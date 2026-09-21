import type { FeatureDataStatus, FeatureReasonCode } from '@/api/types'
import type { Verdict } from '@/routes/report/features/sample'

/**
 * 기능 비교 화면 모델 (S15P21A506-217).
 *
 * 서버 응답(`api/types` 의 `Feature*Wire`)을 그대로 쓰지 않는다. camelCase 변환과 화면이 쓰는
 * 파생값 계산은 `adapter.ts` 한 곳에서 하고, 컴포넌트는 이 파일의 타입만 본다.
 */

/** IA §9.2 — 근거가 충분하면 5~7개. 이보다 적으면 표 상단에 제한 안내를 붙인다. */
export const MIN_FEATURES = 5

export interface VersionChoice {
  version: string
  prerelease: boolean
}

export interface PackageVersions {
  name: string
  /** 정식 버전이 없으면 null — 사전 배포 버전을 대신 고르지 않는다(구상안 §9.1) */
  latestStable: string | null
  /** 최신순 */
  choices: VersionChoice[]
}

export interface FeatureCell {
  packageName: string
  version: string
  verdict: Verdict
  dataStatus: FeatureDataStatus
  evidenceIds: string[]
  note: string | null
  reasonCode: FeatureReasonCode | null
}

export interface FeatureRow {
  id: string
  label: string
  /** 요청한 패키지 순서 */
  cells: FeatureCell[]
}

export interface EnvironmentRow {
  key: string
  label: string
  /** 항목 이름 아래 한 줄 풀이. 용어를 몰라도 무엇을 보는 행인지 알게 한다 */
  hint: string
  /** `packages` 순서. 값이 없으면 null → 화면이 `미확인` 으로 적는다 */
  values: (EnvValue | null)[]
}

export interface NarrativeSection {
  heading: string
  body: string
  evidenceIds: string[]
}

export interface ComparisonPackage {
  name: string
  version: string
}

export interface ComparisonView {
  packages: ComparisonPackage[]
  dataStatus: FeatureDataStatus
  /** 표 상단에 `직접 비교 가능한 기능이 제한적입니다` 를 붙일지 */
  limited: boolean
  /** 비어 있으면 섹션을 그리지 않는다 — 구조화 데이터 계층이 없을 수 있다(구상안 §1.4) */
  environment: EnvironmentRow[]
  environmentNote: string | null
  rows: FeatureRow[]
  narrative: NarrativeSection[]
  narrativeError: string | null
  /** 서버가 세어 준 값. 없으면 셀의 근거 ID 를 중복 없이 센다 */
  evidenceCount: number
  analyzedAt: string
  /** 미리 확인해 둔 예시 결과인지. 분석 서버가 그 자리에서 만든 값이 아니다 */
  isExample: boolean
  /** 다시 시도하면 나아질 수 있는 셀의 수(구상안 §11). 0이면 재시도 버튼을 두지 않는다 */
  retryableCells: number
}

/** 재분석이 끝난 뒤 한 번 보여주는 변경점(구상안 §9.5). 세션 안의 직전 완료 결과와만 비교한다. */
export interface ChangeSummary {
  versionChanges: { name: string; from: string; to: string }[]
  verdictChanges: { feature: string; name: string; from: Verdict; to: Verdict }[]
  evidenceAdded: number
  evidenceRemoved: number
}

/** 구상안 §11 — 미확인 사유. 화면에는 사유만 적고 지원/미지원으로 추정하지 않는다. */
export const REASON_LABEL: Record<FeatureReasonCode, string> = {
  TRANSIENT_FETCH_ERROR: '일시적으로 자료를 받지 못함',
  PARTIAL_SOURCE_FAILURE: '일부 자료를 받지 못함',
  ANALYZER_STALE: '분석기가 갱신되어 새 분석 필요',
  SOURCE_ABSENT: '확인한 자료에서 발견되지 않음',
  EVIDENCE_CONFLICT: '같은 버전 근거가 충돌',
  RUNTIME_REQUIRED: '실행 검증이 필요',
}

/** 다시 시도하면 나아질 수 있는 사유. 나머지는 재시도해도 같은 결과다(구상안 §11). */
export const RETRYABLE_REASONS: ReadonlySet<FeatureReasonCode> = new Set([
  'TRANSIENT_FETCH_ERROR',
  'PARTIAL_SOURCE_FAILURE',
])

/** 셀 판정 아래에 적는 짧은 사유. 없으면 null. */
export function cellReason(cell: FeatureCell): string | null {
  if (cell.reasonCode) return REASON_LABEL[cell.reasonCode]
  if (cell.dataStatus === 'CONFLICT') return REASON_LABEL.EVIDENCE_CONFLICT
  if (cell.dataStatus === 'STALE') return '자료가 오래되어 새 분석 필요'
  if (cell.dataStatus === 'COLLECTION_ERROR') return '자료 수집에 실패함'
  return null
}

/**
 * 근거 ID 하나를 사람이 읽는 출처 이름으로 바꾼다.
 *
 * RAG 의 ID 는 `express@5.2.1#3` · `express@5.2.1#meta-desc` 꼴이다. 기계에는 정확하지만
 * 화면에 그대로 적으면 사용자가 읽을 수 없다. 어느 패키지인지는 표의 열이 이미 말하므로
 * 여기서는 **README 의 어디인지**만 적는다. 원문은 눌러서 Drawer 로 본다.
 */
export function sourceLabel(id: string): string {
  const hash = id.lastIndexOf('#')
  const part = hash >= 0 ? id.slice(hash + 1) : ''
  if (part === 'meta-desc') return '패키지 소개'
  if (part === 'meta-entry') return '불러오는 방식'
  if (part === 'meta-install') return '설치 조건'
  if (part.startsWith('meta-')) return '패키지 정보'
  if (/^\d+$/.test(part)) return `README ${Number(part) + 1}번째 단락`
  return '원문'
}

/** 근거 ID 의 패키지 이름. 스코프 패키지도 있어 `@` 를 `#` 앞에서 뒤로 찾는다. */
export function sourcePackage(id: string): string | null {
  const hash = id.lastIndexOf('#')
  const at = id.lastIndexOf('@', hash >= 0 ? hash : id.length)
  return at > 0 ? id.slice(0, at) : null
}

/** 셀 아래에 적는 출처. 여럿이면 첫 번째만 이름으로 적고 나머지는 개수로 줄인다. */
export function evidenceLabel(cell: FeatureCell): string | null {
  const [first, ...rest] = cell.evidenceIds
  if (!first) return null
  const label = sourceLabel(first)
  return rest.length > 0 ? `${label} 외 ${rest.length}곳` : label
}

/**
 * 소비 조건 칸의 색 톤. 판정(verdict)이 아니다 — 좋고 나쁨이 아니라 **종류**를 구분한다.
 * `unknown` 만 "값을 모른다" 는 뜻이고, 나머지는 전부 확인된 사실이다.
 */
export type EnvTone = 'neutral' | 'positive' | 'info' | 'unknown'

export interface EnvValue {
  text: string
  tone: EnvTone
}
