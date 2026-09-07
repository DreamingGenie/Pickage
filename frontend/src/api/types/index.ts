/**
 * Spring 게이트웨이 DTO.
 *
 * 미확정: 아직 서버 스펙을 못 받아서 화면(Figma 00~03B)에서 역산한 초안이다.
 * 스펙 확정되면 이 파일만 교체하면 되도록 화면 코드는 여기 타입에만 의존시킨다.
 */

export type StatusLevel = 'ok' | 'warn' | 'err'

/** 리포트 생성 단위. id 발급 주체(서버/클라)는 미해결 — 지금은 서버 발급 가정. */
export type ReportId = string

export interface PackageRef {
  /** npm 패키지명 */
  name: string
  /** 사용자가 입력한 버전 레인지 (예: ^18.2.0). 미지정 시 null */
  range: string | null
}

/** 01-package-input: 입력 검증 결과 */
export interface PackageResolution {
  input: PackageRef
  resolved: boolean
  /** 레지스트리에서 확인된 최신 버전 */
  latestVersion: string | null
  /** 해석 실패 사유 */
  reason: string | null
}

/** 02-candidate-select: 대체 후보 */
export interface Candidate {
  name: string
  description: string
  latestVersion: string
  weeklyDownloads: number
  stars: number
  /** 마지막 릴리스 ISO8601 */
  lastPublishedAt: string
  license: string
  /** 0~100 종합 적합도 */
  matchScore: number
}

export interface CandidateListResponse {
  source: PackageRef
  candidates: Candidate[]
}

/** 03A: 생태계 지표 */
export interface EcosystemMetric {
  key: string
  label: string
  value: number
  unit: string | null
  /** 전월 대비 변화율(%) */
  delta: number | null
  status: StatusLevel
}

export interface TimeseriesPoint {
  /** ISO8601 date */
  t: string
  v: number
}

export interface EcosystemSeries {
  key: string
  label: string
  points: TimeseriesPoint[]
}

export interface EcosystemReport {
  reportId: ReportId
  target: PackageRef
  metrics: EcosystemMetric[]
  series: EcosystemSeries[]
}

/** 03B: 기능 비교 */
export interface FeatureCell {
  /** 지원 여부. partial은 제약 있음 */
  support: 'yes' | 'no' | 'partial' | 'unknown'
  note: string | null
  /** 근거 드로어에서 열 evidence id */
  evidenceId: string | null
}

export interface FeatureRow {
  key: string
  label: string
  /** 패키지명 -> 셀 */
  cells: Record<string, FeatureCell>
}

export interface FeatureCompareReport {
  reportId: ReportId
  packages: string[]
  rows: FeatureRow[]
}

/** 근거 드로어 */
export interface Evidence {
  id: string
  title: string
  sourceUrl: string
  excerpt: string
  collectedAt: string
}
