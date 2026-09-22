/**
 * npm 동향 서비스 v1 API 타입.
 *
 * 근거: `npm 동향 서비스 — v1 API 명세` (2026-09-08).
 * 명세의 필드명이 snake_case 라서 **서버 응답 타입은 snake_case 그대로 둔다**.
 * camelCase 로 바꾸는 일은 화면 어댑터(`routes/report/ecosystem/adapter.ts`)가 하고,
 * 이 파일은 서버가 실제로 보내는 모양만 적는다. 여기서 이름을 바꾸면
 * 명세와 코드를 대조할 수 없게 된다.
 */

/* ------------------------------------------------------------------ *
 * 0.3 응답 봉투 · 0.4 에러 코드
 * ------------------------------------------------------------------ */

/** 0.4 — 서버가 정의한 에러 코드. 그 밖의 값은 클라이언트가 만든 것이다. */
export type ApiErrorCode =
  /** 400 필수 파라미터 누락 */
  | 'V001'
  /** 400 개수·범위 상한 초과 */
  | 'V002'
  /** 400 날짜 형식 오류 */
  | 'V003'
  /** 400 값 형식 오류 (길이·문자·타입) */
  | 'V004'
  /** 500 서버 내부 오류 */
  | 'S001'

/** 서버 코드가 아닌, 클라이언트가 자체 판단해 만든 코드. */
export type ClientErrorCode = 'TIMEOUT' | 'NETWORK'

export interface ApiSuccess<T> {
  success: true
  data: T
}

export interface ApiFailure {
  success: false
  code: ApiErrorCode
  message: string
}

export type ApiEnvelope<T> = ApiSuccess<T> | ApiFailure

/* ------------------------------------------------------------------ *
 * 0.1 배치 입력 상한
 * ------------------------------------------------------------------ */

/** 0.1 — `names` 배열 상한. UI 의 최대 선택 수와 같은 값이다. 초과 시 V002. */
export const MAX_NAMES = 3

/*
  §4 — 추이 조회 기간 상한(MAX_WEEKS 104)과 기본 구간(DEFAULT_WEEKS 26)이 여기 있었다.
  서버에서 둘 다 없앴다 — `from`·`to` 를 생략하면 보유한 전 구간이 온다(S15P21A506-374).
  화면이 상한을 알아야 할 이유가 사라져 상수도 함께 지웠다.
*/

/** §2.4 — `limit` 기본값·상한. */
export const SEARCH_LIMIT_DEFAULT = 20
export const SEARCH_LIMIT_MAX = 50

/**
 * 0.1 — npm 이름 허용 문자.
 * 소문자·숫자·`-`·`_`·`.` 와 스코프의 `@`·`/`. 쉼표가 없어 구분자와 충돌하지 않는다.
 */
export const NPM_NAME_RE = /^(?:@[a-z0-9-~][a-z0-9-._~]*\/)?[a-z0-9-~][a-z0-9-._~]*$/

/* ------------------------------------------------------------------ *
 * 2.2 사전 배포 · 2.4 서버 폴백
 * ------------------------------------------------------------------ */

/**
 * 2.2 — 사전 manifest.
 *
 * 파일명을 고정하지 않고 내용 해시를 쓰기 때문에 이 한 겹이 필요하다.
 * `url` 은 immutable 로 캐시되고 manifest 만 짧게 캐시된다.
 */
export interface DictManifest {
  /** 내용 해시가 박힌 사전 파일 경로 */
  url: string
  count: number
  /** YYYY-MM-DD */
  built_at: string
}

/** 2.2 — 사전 파일 본문. 다운로드 상위 N개 이름 배열이며 순서가 곧 인기순이다. */
export type PackageDictionary = string[]

/**
 * 2.4 — 서버 폴백 검색 결과.
 *
 * 이름만 온다. 다운로드 순 정렬이라 배열 순서가 곧 인기순이고,
 * 사전 파일과 형태가 같아 클라이언트가 두 결과를 그대로 합칠 수 있다.
 */
export interface PackageSearchResponse {
  query: string
  items: string[]
}

/* ------------------------------------------------------------------ *
 * 3. GET /packages — 패키지 개요
 * ------------------------------------------------------------------ */

/**
 * 3 — 카드 헤더 + 현재값·증감.
 *
 * 0.5 — 패키지는 있으나 스냅샷이 없으면 `items` 에 들어오고 **지표 필드만 null** 이다.
 * `not_found` 와 구분해야 한다. null 은 0 이 아니라 "집계 대기 중"이다.
 */
export interface PackageOverview {
  name: string
  repo_url: string | null
  latest_version: string
  /** ISO 8601 UTC */
  published_at: string
  description: string | null
  licenses: string[]
  is_deprecated: boolean
  /** 직전 7일 합계. 화면 라벨을 "주간 다운로드"로 고정한다(§3 화면 연결). */
  downloads: number | null
  stars: number | null
  /** 직전 스냅샷 대비 증감. 첫 스냅샷이면 null — 화면에서 화살표를 숨긴다. */
  stars_delta: number | null
  open_issues: number | null
  open_issues_delta: number | null
}

export interface PackagesOverviewResponse {
  /**
   * 0.5 — 항목마다 같으므로 바깥에 한 번만 싣는다. YYYY-MM-DD
   *
   * **적재 전에는 `null` 이다.** 서버가 없는 기준일을 지어내지 않는다 — 화면은 이 값이
   * 없으면 "데이터 축적 중" 으로 그린다. 자료가 없는 것이지 장애가 아니다.
   */
  snapshot_at: string | null
  items: PackageOverview[]
  /** 0.2 — 일부가 없어도 200. 못 찾은 이름을 여기 담는다. */
  not_found: string[]
}

/* ------------------------------------------------------------------ *
 * 4·5. 추이 (downloads · dependents)
 * ------------------------------------------------------------------ */

export interface TrendPoint {
  /** YYYY-MM-DD */
  snapshot_at: string
  value: number
}

/**
 * §4 — 신규 패키지는 옛 스냅샷에 행이 없어 **시리즈마다 길이가 다르다**.
 * x축을 시리즈별 인덱스가 아니라 `snapshot_at` 값으로 잡아야 선이 어긋나지 않는다.
 */
export interface TrendSeries {
  name: string
  /**
   * §5 dependents 전용. **같은 `name` 이 major 개수만큼 반복된다.**
   *
   * downloads 는 버전으로 쪼갤 수 없어 항상 없다. dependents 인데 없으면
   * **그 패키지에 자료가 없다는 뜻**이며(쪼갤 행이 없다), `not_found`(이름 자체가 없음)와
   * 다르다 — 이름은 존재한다.
   *
   * 순서는 서버가 숫자로 세워 보낸 것이다(`'1' < '10' < '2'` 를 피하려고).
   * 화면에서 다시 정렬하지 않는다.
   */
  major?: string
  points: TrendPoint[]
}

export interface DownloadsTrendResponse {
  metric: 'downloads'
  /** 축 라벨의 근거 */
  unit: 'weekly'
  series: TrendSeries[]
  not_found: string[]
}

export interface DependentsTrendResponse {
  metric: 'dependents'
  /**
   * §5 — 그 major 안의 `dependents_count` 를 합산한 값이다.
   * 한 프로젝트가 `^4.17.0` 으로 4.x 의 여러 버전에 걸리므로 **실제 사용처 수보다 크다**.
   * major 로 접어도 그 중복은 그대로다. 기울기는 유효하지만 절대수는 부풀려져 있다 —
   * 축 라벨을 "N개 프로젝트가 사용"으로 쓰면 안 되고 "의존 수(버전별 합계)"로 적는다.
   */
  sum_over_versions: true
  /**
   * **major 별로 쪼개져 온다.** 패키지 카드마다 표시 버전을 독립적으로 고르므로(구상안 §5.2),
   * 고를 때마다 서버에 묻지 않도록 한 번에 다 받는다. `TOTAL` 은 화면에서 날짜별로 더한다.
   */
  series: TrendSeries[]
  not_found: string[]
}

/* ------------------------------------------------------------------ *
 * 기능-14 보고서 PDF
 * ------------------------------------------------------------------ */

/**
 * 문서에 **더할** 구역.
 *
 * 생태계는 여기 없다 — 끌 수 없으므로 고를 것이 아니다. 화면에서는 "생태계" 를 켜진 채
 * 비활성으로 두고, 이 둘만 체크할 수 있게 한다.
 */
export type ReportSection = 'COMMUNITY' | 'FEATURES'

export interface PdfGenerateRequest {
  names: string[]
  from?: string
  to?: string
  snapshot_at?: string
  /**
   * 유지·유입·이탈 조회 구간. 생략하면 서버 기본값(3y) — `from`·`to`(생태계 조회 구간)와는
   * 다른 축이라 그 값으로 대신할 수 없다. 화면이 지금 보여주고 있는 기간과 다르면 PDF가
   * 화면과 다른 숫자를 담게 되므로, 호출부는 항상 현재 선택된 `TransitionPeriod`를 넘겨야
   * 한다(S15P21A506-394).
   */
  period?: TransitionPeriodParam
  sections?: ReportSection[]
}

export interface PdfJob {
  report_id: string
  /**
   * 지금은 항상 `COMPLETE` 다. 생성이 워커로 옮겨가면 `GENERATING` 이 먼저 오고
   * 화면은 그때부터 상태를 다시 물어야 한다 — 그래서 필드를 미리 읽어 둔다.
   */
  status: 'COMPLETE'
  file_name: string
  bytes: number
  created_at: string
  /**
   * 요청했지만 문서에 못 채운 구역. **오류가 아니라** 그 분석 기능이 아직 없는 것이다.
   * 조용히 넘어가면 사용자는 체크한 것이 사라진 이유를 알 수 없다.
   */
  omitted: ReportSection[]
}

/* ------------------------------------------------------------------ *
 * 기능-03 · UC4 유사 패키지
 * ------------------------------------------------------------------ */

export const SIMILAR_LIMIT_DEFAULT = 20
export const SIMILAR_LIMIT_MAX = 50

/**
 * 후보 하나.
 *
 * `package_id` 는 오지 않는다 — 외부 식별자는 이름이다. 다시 조회할 때도 이름을 쓴다.
 */
export interface SimilarCandidate {
  /** 패키지 안에서 유일하다. 배열 순서와 같지만 값도 함께 온다. */
  rank: number
  /**
   * 유사도에 다른 신호를 더한 종합 점수.
   * **비교용 상대값이지 확률이 아니다** — "0.9 = 90% 대체 가능"으로 읽히게 적으면 안 된다.
   */
  score: number
  name: string
  /** 최신 버전. 정보를 못 찾은 후보는 `null` 이며, 그래도 목록에는 남는다. */
  latest_version: string | null
  description: string | null
}

export interface SimilarPackagesResponse {
  /** 요청한 기준 패키지. 화면이 무엇을 물었는지 알아야 한다. */
  base: string
  /**
   * 이 목록을 만든 모델. **스냅샷 날짜 대신 계보를 표시하는 값**이다.
   * 목록이 비면 없다 — 만든 것이 없으므로 지어내지 않는다.
   */
  model_ver?: string
  /**
   * `COMPLETE` 또는 `NO_DATA`.
   * `NO_DATA` 는 **아직 계산되지 않았다**는 뜻이며 오류가 아니다.
   * 이름 자체가 없는 경우(`not_found`)와 구분해야 한다.
   */
  data_status: 'COMPLETE' | 'NO_DATA'
  /** `rank` 오름차순. */
  candidates: SimilarCandidate[]
  not_found: string[]
}

/** 추이 조회 파라미터. `from`·`to` 생략 시 서버가 기본 구간을 정한다. */
export interface TrendQuery {
  names: string[]
  /** YYYY-MM-DD. 생략 시 최신 스냅샷 기준 26주 전 */
  from?: string
  /** YYYY-MM-DD. 생략 시 최신 스냅샷 */
  to?: string
}

/* ------------------------------------------------------------------ *
 * 6. GET /packages/version — 버전 분포
 * ------------------------------------------------------------------ */

export interface VersionSlice {
  /** major 문자열. `0.x` 대는 "0" 으로 뭉친다 — 정상 동작이다. */
  major: string
  dependents: number
  /** §6 — **해당 패키지 안에서의** 비율. 패키지별로 각각 100% 가 된다. */
  pct: number
}

export interface VersionShareItem {
  name: string
  /**
   * 형식은 맞으나 데이터가 없는 `snapshot_at` 이면 빈 배열이다.
   * 이건 에러가 아니라 200 이며, 형식 오류(V003)와 구분해야 한다.
   */
  slices: VersionSlice[]
}

export interface VersionShareResponse {
  /** 요청한 기준일. 생략하면 최신 스냅샷이고, 적재 전이면 `null` 이다. */
  snapshot_at: string | null
  /** 다운로드는 패키지 단위 단일값이라 버전별로 쪼갤 수 없다. 지분 기준은 dependents. */
  basis: 'dependents'
  /** §5 와 같은 이유로 조각 합계는 부풀려진 값이다. 원 가운데에 총계를 찍지 않는다. */
  sum_over_versions: true
  items: VersionShareItem[]
  not_found: string[]
}

/* ------------------------------------------------------------------ *
 * GET /packages/transitions — 유지·유입·이탈 (S15P21A506-361, S15P21A506-391)
 *
 * 근거: `backend/.../domain/packages/dto/TransitionsResponse.java`. 추이(Downloads·
 * Dependents)와 다른 서버 개념이다 — 저건 임의 구간·주간 시계열(SnapshotWindow),
 * 이건 프리셋 3개짜리 단일 스냅샷 비교(TransitionPeriod). 기간 선택기를 공유하지 않는다.
 * ------------------------------------------------------------------ */

export type TransitionPeriodParam = '1y' | '3y' | '5y'
export type TransitionKindWire = 'regular' | 'peer' | 'optional'
export type TransitionDataStatusWire = 'COMPLETE' | 'NO_DATA' | 'OUT_OF_SCOPE' | 'NOT_COMPUTED'

export interface TransitionSeriesItem {
  name: string
  /** 요청한 이름마다 항상 이 순서로 3줄(regular·peer·optional) — 요청 안 해도 전부 온다. */
  kind: TransitionKindWire
  population: 'npm_all'
  /**
   * `data_status`가 행 전체를 지배한다 — COMPLETE·NO_DATA 면 여섯 숫자 필드가 실수치,
   * OUT_OF_SCOPE·NOT_COMPUTED 면 전부 `null`이다(키는 남는다, `ALWAYS` 직렬화). 0 으로
   * 바꾸지 않는다 — null 은 "몰라서 못 셌다", 0 은 "세어 보니 없었다"로 뜻이 다르다.
   */
  retained: number | null
  /** 원시 유입. 93.8~97.5%가 신생 프로젝트라 그대로 "채택"으로 읽으면 안 된다. */
  inflow: number | null
  /** inflow 의 부분집합 — T1 시점엔 아직 존재하지도 않던 패키지. */
  inflow_new: number | null
  /** = inflow - inflow_new, 서버 계산값. 실제 채택 수 — 메인 지표로 쓸 값. */
  inflow_adopted: number | null
  outflow: number | null
  /** 판정 불가(대표 릴리스가 구간 안에서 안 바뀜) — retained 에 합치면 안 된다. */
  unobserved: number | null
  /**
   * `unobserved` 를 그 의존자의 **마지막 대표 릴리스가 t2 에서 얼마나 떨어졌는지**로 쪼갠
   * 셋 (S15P21A506-421). 셋의 합은 언제나 `unobserved` 이며 서버에 DB CHECK 가 걸려 있다.
   * 다섯 번째 범주가 아니라 한 칸의 분해다 — 유지·유입·이탈과 같은 줄에 더해 그리면
   * 합이 두 번 세어진다.
   *
   * **`data_status` 와 독립적으로 `null` 일 수 있다.** 마이그레이션 배포와 88만 행 재적재
   * 사이에는 `COMPLETE` 인데 이 셋만 `null` 인 행이 정상적으로 존재한다(2026-09-21 운영에서
   * 약 30분, 다음 스냅샷 회차마다 다시 생긴다). 그때 0 으로 그리면 "5년 넘게 방치된
   * 의존자가 0명" 이 되어 **숫자가 맞아 보이는 거짓**이 된다.
   */
  unobserved_recent: number | null
  /** 마지막 대표 릴리스가 t2 기준 3~5년 전. */
  unobserved_stale: number | null
  /** 5년 초과 — 사실상 방치. **마지막 릴리스를 모르는 경우도 여기로 센다.** */
  unobserved_dormant: number | null
  data_status: TransitionDataStatusWire
}

export interface TransitionsResponse {
  metric: 'dependent_transitions'
  /** 요청이 생략했으면 서버가 적용한 기본값(3y)을 그대로 돌려준다. */
  period: TransitionPeriodParam
  /** NOT_COMPUTED 가 응답 전체(모든 행)에 해당하면 t1·t2 는 키 자체가 없다. */
  t1?: string
  t2?: string
  series: TransitionSeriesItem[]
  not_found: string[]
}

/* ------------------------------------------------------------------ *
 * S15P21A506-396. 이탈 사유 — 대체 동반 · 대체 없음
 *
 * 근거: `backend/.../domain/packages/dto/RemovalReasonsResponse.java`.
 *
 * **위 `transitions` 와 단위가 다르다.** 구간 프리셋·기본값·기준일은 같지만
 * (서버가 같은 표에서 t1·t2 를 가져온다) 세는 단위가 다르다 —
 * `transitions` 는 **패키지 수**, 이쪽은 **전이 건수**다. 한 의존자가 뺐다 넣었다
 * 다시 뺐으면 `outflow` 는 1 이고 `removals` 는 2 다. **두 응답의 수를 더하거나
 * 나누면 안 된다.**
 * ------------------------------------------------------------------ */

export interface RemovalReasonsSeriesItem {
  name: string
  population: 'npm_all'
  /** 항상 `'transitions'`. 값으로 실려 오므로 캡션에 그대로 쓴다. */
  unit: string
  /**
   * `data_status` 가 행 전체를 지배한다 — COMPLETE·NO_DATA 면 네 숫자가 실수치,
   * OUT_OF_SCOPE·NOT_COMPUTED 면 전부 `null` 이다(키는 남는다). **0 으로 바꾸지 않는다.**
   * 대상 97,745개 중 57,201개(58.5%)가 `NO_DATA` 이므로 이걸 `OUT_OF_SCOPE` 처럼 다루면
   * 대부분의 패키지에 "분석 대상 아님" 이 뜬다.
   */
  removals: number | null
  /** 빼고 아무것도 안 넣은 전이. 어느 구간에서나 약 70%가 여기다 — 이 지표의 결론. */
  no_replacement: number | null
  /** 뺀 릴리스에서 다른 것을 함께 넣은 전이. **같은 자리의 대체라는 보장은 없다.** */
  with_replacement: number | null
  /** 뺀 적 있는 의존자 수(중복 접음). `removals` 와 단위가 달라 나누지 않는다. */
  dependents: number | null
  data_status: TransitionDataStatusWire
}

export interface RemovalReasonsResponse {
  metric: 'removal_reasons'
  period: TransitionPeriodParam
  /** 읽을 행이 없으면 키 자체가 없다 — 서버가 구간에서 날짜를 지어내지 않는다. */
  t1?: string
  t2?: string
  /** **한 패키지가 한 줄이다** — `transitions` 와 달리 `kind` 분해가 없다. */
  series: RemovalReasonsSeriesItem[]
  not_found: string[]
}

/* ------------------------------------------------------------------ *
 * S15P21A506-424. 관측된 교체 흐름 — 어디로 갔나
 *
 * 근거: `backend/.../domain/packages/dto/MigrationPairsResponse.java`.
 *
 * **위 둘과 또 단위가 다르다.** `transitions` 는 패키지 수, `removal_reasons` 는
 * 전이 건수, 이쪽은 **가중 표(votes)** 다. 셋을 더하거나 비율을 내면 안 된다.
 *
 * **구간(period)이 없다.** 시점 두 개를 비교하는 것이 아니라 연속한 릴리스를 전부 훑은
 * 것이라 "몇 년치" 라는 축이 성립하지 않는다. 대신 `kind` 로 원천을 고른다.
 * ------------------------------------------------------------------ */

/** 어느 의존 칸에서 관측했나. 두 값은 **모집단이 다른 별개의 실행**이다. */
export type DependencyKindParam = 'regular' | 'dev'

export const DEFAULT_DEPENDENCY_KIND: DependencyKindParam = 'regular'

export type MigrationDataStatusWire =
  'COMPLETE' | 'INSUFFICIENT_EVIDENCE' | 'NO_DATA' | 'OUT_OF_SCOPE' | 'NOT_COMPUTED'

export interface MigrationDestinationWire {
  name: string
  /** 가중 표. 정수가 아니다(소수 한 자리). */
  votes: number
  co_events: number
  publisher_months: number
  dependents: number
  /** 모집단 대비 배수. **다른 `kind` 와 절댓값을 비교하지 말 것** — 분모가 그 실행의 전이 수다. */
  lift: number
  /** 점유율. 분모는 표가 아니라 (발행자 × 달) 의 수다. **합이 100 이 아니다** — 아래 참고. */
  share_pm_pct: number
  /** 표 기준 점유율. 등급 판정의 입력이라 함께 오지만 **화면에 쓰지 않는다.** */
  share_pct: number
  /**
   * 그 패키지를 뺀 전이 중 이것을 함께 넣은 비율. **`share_pm_pct` 와 분모가 다르다** —
   * 이쪽은 이탈 전체가 분모라 "뺀 사람 다섯 중 하나가 이걸 골랐다" 로 읽힌다.
   */
  a_pct: number
  /** `strict` · `recommended` · `loose`. 행을 지우는 대신 붙이는 배지다. */
  evidence: string
  /** 양방향 관측. **같은 물건의 두 포장**일 수 있다(lodash ↔ lodash-es). 지우지 말고 구분만 한다. */
  variant: boolean
  first_seen: string
  last_seen: string
}

/** 상위 밖을 접은 칸. 이름을 세우지 않는 이유는 꼬리의 82%가 일회성 추가라서다. */
export interface MigrationEtcWire {
  pairs: number
  share_pm_pct: number
  /** 그중 기본 필터에 못 미친 수. "근거가 약해 접었다" 를 말할 근거. */
  below_filter: number
}

export interface MigrationSeriesItem {
  name: string
  /** 이 종류의 기준일. `kind` 마다 다르다(regular 08-31 · dev 09-16). 읽을 행이 없으면 null. */
  snapshot_at: string | null
  /** 항상 `'publisher_months'`. 점유율 분모가 표가 아니라는 표시다. 값으로 오므로 캡션에 쓴다. */
  share_basis: string
  /** 기본 필터를 통과한 상위 5개. `INSUFFICIENT_EVIDENCE` 면 빈 배열이다. */
  destinations: MigrationDestinationWire[]
  /** 접을 것이 없으면 null. */
  etc: MigrationEtcWire | null
  /** 필터 전 관측된 쌍의 수. 세어 보지 않은 상태면 null. */
  observed_pairs: number | null
  data_status: MigrationDataStatusWire
}

export interface MigrationPairsResponse {
  metric: 'migration_pairs'
  /** 요청이 생략했으면 서버가 적용한 기본값(regular)을 그대로 돌려준다. */
  kind: DependencyKindParam
  series: MigrationSeriesItem[]
  not_found: string[]
}

/* ------------------------------------------------------------------ *
 * GitHub 커뮤니티 현황 (S15P21A506-316)
 *
 * 근거: `docs/for_community/Pickage_GitHub커뮤니티_구현계획_260908.md` §6 +
 * 실제 `backend/.../domain/community` DTO(더 신뢰도 높은 근거). 위 섹션과 같은 이유로
 * snake_case 그대로 둔다 — camelCase 변환은 `routes/report/community/adapter.ts`가 한다.
 * ------------------------------------------------------------------ */

export type CommunityViewStatus = 'IDLE' | 'PROCESSING' | 'RESULT' | 'FAILED'
export type CommunityFreshness = 'FRESH' | 'STALE'
export type CommunityRefreshTrigger = 'ANALYSIS_CONFIRMED' | 'TAB_OPENED'
export type CommunityRefreshStatus =
  'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CAPACITY_LIMITED'
export type CommunityRefreshStage =
  | 'VERIFYING_REPOSITORY'
  | 'SEARCHING_ISSUES'
  | 'COLLECTING_COMMENTS'
  | 'SUMMARIZING'
  | 'VALIDATING'
  | 'PUBLISHING'
export type CommunityErrorCode =
  | 'GITHUB_RATE_LIMITED'
  | 'GITHUB_UNAVAILABLE'
  | 'NPM_UNAVAILABLE'
  | 'GMS_UNAVAILABLE'
  | 'REFRESH_DEADLINE_EXCEEDED'
  | 'PUBLISH_FAILED'
  | 'CAPACITY_LIMITED'
  | 'LOCAL_RATE_LIMITED'
  | 'COMMUNITY_DISABLED'
export type CommunityDataStatus =
  | 'AVAILABLE'
  | 'PARTIAL'
  | 'UNVERIFIED_REPOSITORY'
  | 'AMBIGUOUS_SCOPE'
  | 'UNSUPPORTED_HOST'
  | 'NO_DISCUSSION_DATA'
export type CommunitySummaryStatus = 'READY' | 'PARTIAL' | 'FAILED' | 'SKIPPED'
export type CommunityCollectionStatus = 'COMPLETE' | 'TRUNCATED' | 'FAILED'
export type CommunityRepositoryScope = 'PACKAGE_SCOPED' | 'REPOSITORY_WIDE'
export type CommunityMessageRole =
  'ISSUE_AUTHOR' | 'REPOSITORY_OWNER' | 'ORGANIZATION_MEMBER' | 'COLLABORATOR' | 'CONTRIBUTOR'
export type CommunityMessageKind = 'DISCUSSION' | 'USER_SOLUTION'

/** 서버가 고정 한국어 문구를 만드는 한계 코드. 문구는 `message`로 그대로 온다 — 화면에서 다시 만들지 않는다. */
export type CommunityLimitationCode =
  | 'REPOSITORY_SOURCE_CONFLICT'
  | 'REPOSITORY_WIDE_SCOPE'
  | 'ROOT_PACKAGE_SCOPE_HEURISTIC'
  | 'NPM_REPOSITORY_ONLY'
  | 'REPOSITORY_ARCHIVED'
  | 'SEARCH_INCOMPLETE'
  | 'ISSUE_FILTERED'
  | 'COMMENTS_TRUNCATED'
  | 'COMMENTS_UNAVAILABLE'
  | 'SUMMARY_INPUT_LIMITED'
  | 'SUMMARY_UNAVAILABLE'
  | 'RESPONSE_SIZE_LIMITED'

export interface CommunityRepository {
  owner: string
  name: string
  full_name: string
  scope: CommunityRepositoryScope
  archived: boolean
  /**
   * 저장소 **전체** Issue 수(PR 제외)와 그중 열려 있는 수(S15P21A506-413). 요약한 Issue 몇 건이 아니라 저장소 규모다.
   * 서버가 못 구했거나(`null`) 이 값을 더하기 전에 저장된 스냅샷이면(키 없음) 비어 있다 — 화면은 둘을 같게 다룬다.
   */
  issue_count?: number | null
  open_issue_count?: number | null
}

export interface CommunitySummary {
  issue_count: number
  open_issue_count: number
  comment_count: number
  reaction_count: number
}

export interface CommunityMessage {
  author_login: string | null
  role: CommunityMessageRole | null
  kind: CommunityMessageKind
  /** ISO 8601 UTC */
  created_at: string
  text: string
}

/**
 * 요약문(`summary_ko`) 안의 강조 구간. 서버가 계산한 UTF-16 오프셋 `[start, end)` 라 JS `String.slice` 와 같은 단위다
 * (S15P21A506-408). `KEY_TERM` 은 핵심어(굵게), `KEY_SENTENCE` 는 핵심 문장(형광펜)이다.
 */
export interface CommunitySummaryMark {
  start: number
  end: number
  kind: 'KEY_TERM' | 'KEY_SENTENCE'
}

/**
 * Issue 하나. `title_ko`/`summary_ko`가 없으면 요약이 실패한 것 — `title_original`만 보여준다.
 *
 * 논의 흐름(`flow`)은 없다. 화면이 그리지 않아 서버도 만들지도 내려주지도 않는다(S15P21A506-412).
 * 옛 서버 응답에 남아 있어도 이 화면은 읽지 않는다.
 */
export interface CommunityTopic {
  issue_number: number
  state: 'OPEN' | 'CLOSED'
  /** ISO 8601 UTC */
  updated_at: string
  /** ISO 8601 UTC */
  created_at: string
  /** 최대 200자로 잘려 온다 */
  title_original: string
  title_ko: string | null
  comments_count: number
  reactions_count: number
  collection_status: CommunityCollectionStatus
  summary_status: CommunitySummaryStatus
  summary_ko: string | null
  /** 최대 4개 */
  messages: CommunityMessage[]
  /** 요약문의 강조 구간. 없거나 비어 있으면 강조 없이 평문으로 보인다(이전 스냅샷) */
  summary_marks: CommunitySummaryMark[]
}

export interface CommunityLimitation {
  code: CommunityLimitationCode
  /** 서버 템플릿이 만든 한국어 문구. 화면은 이걸 그대로 보여준다 */
  message: string
  issue_number: number | null
}

export interface CommunityDataLimits {
  policy_version: string
  lookback_days: 180 | 365
  max_issues: number
  max_comments_per_issue: number
  max_messages_per_issue: number
  source_note: string
}

export interface CommunityResult {
  snapshot_id: string
  /** ISO 8601 UTC */
  collected_at: string
  /** ISO 8601 UTC */
  fresh_until: string
  /** ISO 8601 UTC */
  serve_until: string
  data_status: CommunityDataStatus
  summary_status: CommunitySummaryStatus
  /** ISO 8601 UTC. 전체 요약 실패가 아니면 null */
  summary_retry_at: string | null
  /** 검증 실패로 terminal 상태가 된 경우 null */
  repository: CommunityRepository | null
  summary: CommunitySummary
  topics: CommunityTopic[]
  limitations: CommunityLimitation[]
  data_limits: CommunityDataLimits
}

export interface CommunityRefreshInfo {
  refresh_id: string | null
  status: CommunityRefreshStatus
  /** RUNNING 일 때만 값이 있다 */
  stage: CommunityRefreshStage | null
  /** 서버가 만든 고정 한국어 문구. 가짜 진행률이 아니다 — 화면은 이 문구를 그대로 쓴다 */
  stage_message: string
  /** ISO 8601 UTC. worker 시작 전이면 null */
  started_at: string | null
  /** ISO 8601 UTC */
  last_updated_at: string
  /** QUEUED/RUNNING 일 때만 값(초), 그 외 null */
  poll_after_seconds: number | null
  /** ISO 8601 UTC. 재시도 가능 시각 */
  retry_at: string | null
  error_code: CommunityErrorCode | null
}

export interface CommunityStatusResponse {
  package_name: string
  view_status: CommunityViewStatus
  freshness: CommunityFreshness | null
  refresh: CommunityRefreshInfo | null
  result: CommunityResult | null
}

/* ------------------------------------------------------------------ *
 * 기능 비교 [확장] (S15P21A506-217)
 *
 * ⚠ pending API alignment — Notion API 명세에 아직 없다. 구상안 §7·§9·§10 과
 * `ai/rag/main.py` 의 `/compare` 응답을 wire 규칙(snake_case)으로 옮긴 **임시안**이다.
 * BE 연동(S15P21A506-130·313)이 확정되면 이 절을 명세에 맞춰 고친다. 화면은 이 타입이
 * 아니라 `routes/report/features/adapter.ts` 가 만든 도메인 모델만 본다.
 * ------------------------------------------------------------------ */

/** 구상안 §7.2. `UNSUPPORTED` 는 공식 부정 근거가 연결됐을 때만 쓴다. */
export type FeatureVerdict =
  'SUPPORTED' | 'CONDITIONALLY_SUPPORTED' | 'LIMITED_SUPPORT' | 'UNCONFIRMED' | 'UNSUPPORTED'

/** 구상안 §7.2. verdict 와 다른 축이다 — 섞지 않는다. */
export type FeatureDataStatus =
  'COMPLETE' | 'PARTIAL' | 'NO_DATA' | 'COLLECTION_ERROR' | 'CONFLICT' | 'STALE'

/** 구상안 §11 — 미확인 사유. UI 행동(재시도 여부)이 여기서 갈린다. */
export type FeatureReasonCode =
  | 'TRANSIENT_FETCH_ERROR'
  | 'PARTIAL_SOURCE_FAILURE'
  | 'ANALYZER_STALE'
  | 'SOURCE_ABSENT'
  | 'EVIDENCE_CONFLICT'
  | 'RUNTIME_REQUIRED'

/** 분석 요청·응답 모두에서 쓰는 (패키지, 정확한 버전) 쌍. */
export interface FeatureTarget {
  package_name: string
  version: string
}

/* ------------------------------------------------------------------ *
 * 화면 전용 타입 (서버 스펙 아님)
 * ------------------------------------------------------------------ */

/**
 * UI 뱃지 등급. 명세에 없는 화면 전용 값이다.
 * 서버는 판정을 내리지 않으므로 이 값은 클라이언트가 관측치로부터 정한다.
 */
export type StatusLevel = 'ok' | 'warn' | 'err'

/**
 * 입력창이 다루는 패키지 참조.
 *
 * `range` 는 v1 API 가 받지 않는다(마이그레이션 판정 UC3 은 제외 확정).
 * 입력 파싱 결과를 보존하기 위해 남겨 두되, API 호출에는 `name` 만 쓴다.
 */
export interface PackageRef {
  name: string
  /** 사용자가 입력한 버전 레인지 (예: ^18.2.0). 미지정 시 null */
  range: string | null
}

/* ------------------------------------------------------------------ *
 * 버전별 소비 조건 · 기능 비교 run (BE S15P21A506-130)
 *
 * 217 이 처음 잡았던 `FeatureComparisonResponse.environment` 와 다르다. 백엔드가 이 둘을
 * **다른 엔드포인트**로 나눴기 때문이다 — 소비 조건은 배치가 미리 접어 둔 표를 키 조회하는
 * 것이라 즉시 뜨고, 기능 비교는 LLM 생성이 붙어 분 단위로 간다. 묶으면 확인된 사실까지
 * 생성이 끝날 때까지 못 보여 준다(기능-10-R06).
 * ------------------------------------------------------------------ */

/** `UNKNOWN` 은 판정 실패가 아니라 unpublish 된 버전이라 선언을 못 본 것이다. */
export type PackageModuleFormat = 'CJS' | 'ESM_ONLY' | 'ESM_CJS' | 'UNKNOWN'

export interface PackageEnvItemWire {
  name: string
  version: string
  module_format: PackageModuleFormat
  /** 거짓은 "타입 없음" 이 아니라 "이 패키지 안에는 없음" 이다 — `@types/xxx` 를 따로 깐다 */
  types_bundled: boolean
  /** 전이 의존이 아니다. null 은 0 이 아니라 모름(unpublish) */
  direct_dependencies: number | null
  /** 사용자가 이미 갖고 있어야 하는 조건. direct 와 더하지 않는다 */
  peer_dependencies: number | null
}

/**
 * `GET /api/packages/versions` — 기능 비교 버전 드롭다운 (기능-10-R02, BE S15P21A506-432).
 *
 * `GET /api/packages/version`(단수, major 지분)과 다른 API 다. 이쪽은 정확한 버전 문자열이다.
 * 올라오는 버전은 **전부 소비 조건(`package_env`)이 있는 정식 버전**이라, 어느 것을 골라도
 * 핵심 비교 요약이 채워진다.
 */
export interface FeatureVersionsResponse {
  /** 요청한 순서 그대로 */
  packages: {
    package_name: string
    /** 드롭다운 기본값. `versions` 의 맨 앞. 고를 버전이 없으면 null */
    latest_stable: string | null
    /** 최신순, 최대 3개 */
    versions: string[]
  }[]
  /** `package` 에 이름 자체가 없는 것 */
  not_found: string[]
}

export interface PackageEnvResponse {
  /** 요청한 순서 그대로 */
  items: PackageEnvItemWire[]
  /** 표에 행이 없는 `이름@버전`. 일부가 없어도 200 이다 */
  not_found: string[]
}

export type FeatureRunStatus = 'RUNNING' | 'COMPLETED' | 'FAILED'

/** 백엔드가 실제로 지나는 단계. 프런트의 여섯 칸과 대응하지 않는다 */
export type FeatureRunPhase = 'PREPARING_DOCS' | 'COMPARING' | 'DONE'

/** `VERIFICATION_FAILED` 는 재시도해도 같은 답이 나올 수 있다 — 재시도가 없는 파이프라인이다 */
export type FeatureRunErrorCode =
  'DOC_NOT_FOUND' | 'VERIFICATION_FAILED' | 'RAG_UNAVAILABLE' | 'INTERRUPTED'

/**
 * RAG 서버 응답 원본.
 *
 * **여기만 camelCase 다.** 백엔드가 이 값을 우리 타입으로 옮기지 않고 그대로 통과시킨다 —
 * 계약의 주인이 `ai/rag/main.py` 이고, 옮기면 백엔드의 snake_case 전략이 `featureLabel` 을
 * `feature_label` 로 바꿔 AI 가 정한 이름과 달라진다.
 */
export interface RagComparisonResult {
  dataStatus: 'COMPLETE' | 'COMPARISON_LIMITED'
  packages: { package: string; version: string }[]
  features: {
    featureLabel: string
    results: {
      package: string
      version: string
      verdict: FeatureVerdict
      evidenceIds: string[]
      groundedIn: 'EVIDENCE' | 'GENERAL_KNOWLEDGE'
      note: string | null
    }[]
  }[]
  narrative: { heading: string; body: string; evidenceIds: string[] }[]
  narrativeError: string | null
  /** 패키지별 인계 파일 상태. dataStatus 와 다른 축이다 */
  sources: {
    package: string
    version: string
    status: 'OK' | 'LIMITED' | 'NONE' | null
    readmeBytes: number | null
    proseChars: number | null
  }[]
}

export interface FeatureRunResponse {
  run_id: string
  status: FeatureRunStatus
  phase: FeatureRunPhase
  /** `이름@버전` */
  refs: string[]
  elapsed_sec: number
  /** COMPLETED 일 때만 */
  result: RagComparisonResult | null
  /** FAILED 일 때만 */
  error_code: FeatureRunErrorCode | null
  error_detail: unknown
}
