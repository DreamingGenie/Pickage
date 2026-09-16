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

/** §4 — 추이 조회 기간 상한(주). 배열 상한 3 과 곱해져 응답 크기를 정한다. */
export const MAX_WEEKS = 104

/** §4 — `from` 생략 시 기본 구간(주). */
export const DEFAULT_WEEKS = 26

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
}

export interface CommunitySummary {
  issue_count: number
  open_issue_count: number
  comment_count: number
  reaction_count: number
}

export interface CommunityFlowStep {
  text: string
}

export interface CommunityMessage {
  author_login: string | null
  role: CommunityMessageRole | null
  kind: CommunityMessageKind
  /** ISO 8601 UTC */
  created_at: string
  text: string
}

/** Issue 하나. `title_ko`/`summary_ko`가 없으면 요약이 실패한 것 — `title_original`만 보여준다. */
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
  flow: CommunityFlowStep[]
  /** 최대 3개 */
  messages: CommunityMessage[]
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
