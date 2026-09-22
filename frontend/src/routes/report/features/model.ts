/**
 * 기능 비교 화면 모델 (S15P21A506-217).
 *
 * 서버 응답을 그대로 쓰지 않는다. 변환은 `rag-adapter.ts`·`environment-adapter.ts` 에서 하고,
 * 컴포넌트는 이 파일의 타입만 본다.
 */

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

export interface EnvironmentRow {
  key: string
  label: string
  /** 항목 이름 아래 한 줄 풀이. 용어를 몰라도 무엇을 보는 행인지 알게 한다 */
  hint: string
  /** `packages` 순서. 값이 없으면 null → 화면이 `미확인` 으로 적는다 */
  values: (EnvValue | null)[]
}

/** 패키지 하나의 차이점 서술 */
export interface PackageDifference {
  name: string
  version: string
  body: string
}

export interface ComparisonPackage {
  name: string
  version: string
}

/**
 * AI 기능 비교 결과 — 공통점 한 덩어리와 패키지별 차이점 문단 (2026-09-22, 판정표 대신).
 */
export interface ComparisonView {
  packages: ComparisonPackage[]
  /** AI 가 자료가 부족해 제대로 서술하지 못했다고 알린 경우 */
  limited: boolean
  common: string
  /** `packages` 순서 */
  differences: PackageDifference[]
  analyzedAt: string
}

/** 재분석이 끝난 뒤 한 번 보여주는 변경점(구상안 §9.5). 세션 안의 직전 완료 결과와만 비교한다. */
export interface ChangeSummary {
  versionChanges: { name: string; from: string; to: string }[]
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
