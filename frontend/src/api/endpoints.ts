/**
 * 엔드포인트 한 겹.
 *
 * **분기는 여기 한 곳에서만 일어난다.** 화면과 쿼리 훅은 mock 여부를 모른다 —
 * 알게 되면 서버를 붙일 때 화면 코드까지 손봐야 하고, mock 에서만 되는 동작이
 * 조용히 화면에 스며든다.
 *
 * 켜기: `.env.local` 에 `VITE_USE_MOCK=true`
 */

import { API_BASE_URL, get, getRaw, getText, post } from '@/api/client'
import { mockCommunityRefresh, mockCommunityStatus } from '@/api/mock/community'
import {
  mockFeatureRun,
  mockFeatureVersions,
  mockPackageEnv,
  mockStartFeatureRun,
} from '@/api/mock/features'
import {
  mockDependentsTrend,
  mockDictManifest,
  mockDictionary,
  mockDownloadsTrend,
  mockGeneratePdf,
  mockPackagesOverview,
  mockPdfPreview,
  mockSearch,
  mockSimilarPackages,
  mockMigrationPairs,
  mockRemovalReasons,
  mockTransitions,
  mockVersionShare,
} from '@/api/mock/handlers'
import type {
  CommunityRefreshTrigger,
  CommunityStatusResponse,
  DependencyKindParam,
  DependentsTrendResponse,
  DictManifest,
  DownloadsTrendResponse,
  FeatureTarget,
  FeatureRunResponse,
  FeatureVersionsResponse,
  MigrationPairsResponse,
  PackageEnvResponse,
  PackageDictionary,
  PackageSearchResponse,
  PackagesOverviewResponse,
  PdfGenerateRequest,
  PdfJob,
  SimilarPackagesResponse,
  TransitionPeriodParam,
  RemovalReasonsResponse,
  TransitionsResponse,
  TrendQuery,
  VersionShareResponse,
} from '@/api/types'

/**
 * 문자열 비교로 판정한다. Vite 의 `import.meta.env` 값은 항상 문자열이라
 * `Boolean(env.VITE_USE_MOCK)` 로 쓰면 `"false"` 도 참이 된다.
 */
export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

/* ------------------------------------------------------------------ *
 * 2.2 사전 · 2.4 검색
 * ------------------------------------------------------------------ */

/** 2.2 — manifest 는 짧게 캐시된다(max-age=300). 사전 파일 경로는 여기서만 얻는다. */
export function fetchDictManifest(): Promise<DictManifest> {
  return USE_MOCK ? mockDictManifest() : get<DictManifest>('/dict-manifest')
}

/**
 * 2.2 — 사전 파일 본문.
 *
 * manifest 가 준 URL 을 **그대로** 쓴다. 경로를 조립하면 내용 해시가 깨져
 * immutable 캐시의 의미가 없어진다. 봉투도 쓰지 않는 정적 파일이다.
 */
export function fetchDictionary(url: string): Promise<PackageDictionary> {
  return USE_MOCK ? mockDictionary() : getRaw<PackageDictionary>(url)
}

/** 2.4 — 사전에 없는 이름을 위한 서버 폴백. 접두사 검색만 한다. */
export function fetchPackageSearch(q: string, limit?: number): Promise<PackageSearchResponse> {
  return USE_MOCK
    ? mockSearch(q, limit)
    : get<PackageSearchResponse>('/packages/search', { q, limit })
}

/* ------------------------------------------------------------------ *
 * 3. 개요
 * ------------------------------------------------------------------ */

export function fetchPackagesOverview(names: readonly string[]): Promise<PackagesOverviewResponse> {
  return USE_MOCK
    ? mockPackagesOverview(names)
    : get<PackagesOverviewResponse>('/packages', { names })
}

/* ------------------------------------------------------------------ *
 * 4·5. 추이
 * ------------------------------------------------------------------ */

export function fetchDownloadsTrend(query: TrendQuery): Promise<DownloadsTrendResponse> {
  return USE_MOCK
    ? mockDownloadsTrend(query)
    : get<DownloadsTrendResponse>('/packages/downloads', {
        names: query.names,
        from: query.from,
        to: query.to,
      })
}

export function fetchDependentsTrend(query: TrendQuery): Promise<DependentsTrendResponse> {
  return USE_MOCK
    ? mockDependentsTrend(query)
    : get<DependentsTrendResponse>('/packages/dependents', {
        names: query.names,
        from: query.from,
        to: query.to,
      })
}

/* ------------------------------------------------------------------ *
 * 기능-14. 보고서 PDF
 * ------------------------------------------------------------------ */

/**
 * 문서를 만든다.
 *
 * 숫자가 아니라 **조건**을 보낸다 — 서버가 다시 조회하므로 화면이 들고 있던 옛 응답이
 * 문서에 박히지 않는다(공통-R08).
 */
export function generatePdf(request: PdfGenerateRequest): Promise<PdfJob> {
  return USE_MOCK ? mockGeneratePdf(request) : post<PdfJob>('/report/pdf', request)
}

/**
 * 미리보기 **HTML**. PDF 가 아니다.
 *
 * PDF 를 `iframe` 에 넣으면 브라우저의 "PDF 다운로드" 설정에 걸려 저장창이 뜬다.
 * 서버가 `inline` 으로 보내도 그 설정이 이긴다. 그래서 문서 내용을 그린 HTML 을 받아
 * 모달이 직접 띄운다.
 *
 * **다운로드할 PDF 와 같은 생성에서 나온 HTML 이다** — PDF 는 이것을 변환한 것이라
 * 둘이 갈릴 수 없다.
 */
export function fetchPdfPreview(reportId: string): Promise<string> {
  return USE_MOCK ? mockPdfPreview(reportId) : getText(`/report/pdf/${reportId}/preview`)
}

/**
 * 다운로드 주소.
 *
 * 여기만 `fetch` 가 아니라 **주소를 그대로 쓴다.** 서버가 `attachment` 로 보내므로
 * 링크를 열면 브라우저가 저장한다. blob 을 만들 이유가 없다 — 만들면 같은 파일을
 * 메모리에 한 번 더 들고 있게 되고 해제까지 챙겨야 한다.
 */
export function pdfDownloadUrl(reportId: string): string {
  return `${API_BASE_URL}/report/pdf/${reportId}/file`
}

/* ------------------------------------------------------------------ *
 * 기능-03 · UC4. 유사 패키지
 * ------------------------------------------------------------------ */

/**
 * 기준 패키지의 대체 후보.
 *
 * **`names` 배열이 아니라 `name` 하나다.** "무엇의 대체재인가" 를 묻는 조회라 기준이 둘일 수
 * 없고, 최대 3개 상한은 비교 화면의 규칙이라 여기와 무관하다.
 *
 * 후보가 없는 것과 이름이 없는 것을 구분해야 한다 — 앞은 `data_status: 'NO_DATA'` 이고
 * 뒤는 `not_found` 다. 둘을 같은 문구로 그리면 "아직 계산 전" 이 "이름을 확인하세요" 로 뜬다.
 */
export function fetchSimilarPackages(
  name: string,
  limit?: number,
): Promise<SimilarPackagesResponse> {
  return USE_MOCK
    ? mockSimilarPackages(name, limit)
    : get<SimilarPackagesResponse>('/packages/similar', { name, limit })
}

/* ------------------------------------------------------------------ *
 * 6. 버전 분포
 * ------------------------------------------------------------------ */

export function fetchVersionShare(
  names: readonly string[],
  snapshotAt?: string,
): Promise<VersionShareResponse> {
  return USE_MOCK
    ? mockVersionShare(names, snapshotAt)
    : get<VersionShareResponse>('/packages/version', { names, snapshot_at: snapshotAt })
}

/* ------------------------------------------------------------------ *
 * S15P21A506-361·391. 유지·유입·이탈
 *
 * 추이(4·5)와 별도 섹션인 이유: `names`·`from`·`to` 로 임의 구간을 잘라 주는 추이와
 * 달리, 여기는 `period` 프리셋(1y·3y·5y) 세 개짜리 서버 계산이다. `TrendQuery`를
 * 재사용하지 않는다 — 모양이 우연히 비슷해도 서버가 받는 계약이 다르다.
 * ------------------------------------------------------------------ */

export function fetchTransitions(
  names: readonly string[],
  period?: TransitionPeriodParam,
): Promise<TransitionsResponse> {
  return USE_MOCK
    ? mockTransitions(names, period)
    : get<TransitionsResponse>('/packages/transitions', { names, period })
}

/* ------------------------------------------------------------------ *
 * S15P21A506-396·410. 이탈 사유
 *
 * 위와 **같은 프리셋·같은 기준일**이지만 단위가 다르다(패키지 수 vs 전이 건수).
 * 같은 `period` 값을 그대로 보내도 되는 이유는 서버가 두 표에서 같은 `t1`·`t2` 를
 * 꺼내기 때문이다 — 화면이 두 패널에 한 선택기를 공유하는 근거가 여기다.
 * ------------------------------------------------------------------ */

export function fetchRemovalReasons(
  names: readonly string[],
  period?: TransitionPeriodParam,
): Promise<RemovalReasonsResponse> {
  return USE_MOCK
    ? mockRemovalReasons(names, period)
    : get<RemovalReasonsResponse>('/packages/removal-reasons', { names, period })
}

/* ------------------------------------------------------------------ *
 * S15P21A506-424. 관측된 교체 흐름 — 어디로 갔나
 *
 * 위 둘과 달리 **`period` 를 받지 않는다.** 연속한 릴리스를 전부 훑은 결과라 구간이라는
 * 축이 없다. 대신 `kind` 로 원천을 고르는데, 두 값은 모집단이 다른 별개의 실행이라
 * 한 요청이 한 종류만 받는다 — 섞이면 비교할 수 없는 수가 한 분포에 들어간다.
 * ------------------------------------------------------------------ */

export function fetchMigrationPairs(
  names: readonly string[],
  kind?: DependencyKindParam,
): Promise<MigrationPairsResponse> {
  return USE_MOCK
    ? mockMigrationPairs(names, kind)
    : get<MigrationPairsResponse>('/packages/migration-pairs', { names, kind })
}

/* ------------------------------------------------------------------ *
 * S15P21A506-316. GitHub 커뮤니티 현황
 * ------------------------------------------------------------------ */

/** 부작용 없음. GET 은 수집을 시작하지 않는다(구현계획 §2). */
export function fetchCommunityStatus(
  name: string,
  signal?: AbortSignal,
): Promise<CommunityStatusResponse> {
  return USE_MOCK
    ? mockCommunityStatus(name)
    : get<CommunityStatusResponse>('/packages/community', { name }, { signal })
}

/**
 * body 가 없고 `name`·`trigger` 둘 다 query string 이다(§6.1) — `post()`에 `params`로 넘긴다.
 * 새 task 수락(202) 또는 기존 상태 반환(200) 모두 같은 봉투이므로 화면은 HTTP status 를
 * 보지 않는다. **재시도하지 않는다**(§8.1) — react-query 훅 쪽에서 `retry: false`로 강제한다.
 */
export function postCommunityRefresh(
  name: string,
  trigger: CommunityRefreshTrigger,
): Promise<CommunityStatusResponse> {
  return USE_MOCK
    ? mockCommunityRefresh(name, trigger)
    : post<CommunityStatusResponse>('/packages/community/refresh', undefined, {
        params: { name, trigger },
      })
}

/* ------------------------------------------------------------------ *
 * S15P21A506-217. 기능 비교 [확장] — BE S15P21A506-130 연동 완료
 *
 * 소비 조건과 AI 비교가 **다른 엔드포인트**다(기능-10-R06). 앞은 키 조회라 즉시 뜨고,
 * 뒤는 LLM 생성이 붙어 시작과 조회가 나뉜다.
 *
 * 버전 드롭다운은 `GET /api/packages/versions`(BE S15P21A506-432)가 준다.
 * ------------------------------------------------------------------ */

/** 기능 비교 버전 드롭다운. 소비 조건이 있는 최근 정식 버전만 온다(BE S15P21A506-432). */
export function fetchFeatureVersions(names: readonly string[]): Promise<FeatureVersionsResponse> {
  return USE_MOCK
    ? mockFeatureVersions(names)
    : get<FeatureVersionsResponse>('/packages/versions', { names })
}

/**
 * 버전별 소비 조건 (기능-11-R01, BE S15P21A506-130).
 *
 * 기능 비교와 **다른 엔드포인트**다. 이건 배치가 미리 접어 둔 표를 키 조회하는 것이라
 * 즉시 뜨고, 기능 비교는 LLM 을 기다린다. 묶으면 확인된 사실까지 늦어진다.
 *
 * 일부가 없어도 200 이고 `not_found` 로 온다 — 완료 판단이 "확인된 정보만 표시" 다.
 */
export function fetchPackageEnv(targets: readonly FeatureTarget[]): Promise<PackageEnvResponse> {
  const refs = targets.map((t) => `${t.package_name}@${t.version}`)
  return USE_MOCK ? mockPackageEnv(refs) : get<PackageEnvResponse>('/packages/env', { refs })
}

/**
 * 기능 비교를 시작한다. **결과를 기다리지 않는다** — LLM 생성이 붙어 nginx 60초를 넘길 수 있다.
 * 돌려받은 `run_id` 로 아래 조회를 폴링한다.
 */
export function startFeatureRun(targets: readonly FeatureTarget[]): Promise<FeatureRunResponse> {
  const refs = targets.map((t) => `${t.package_name}@${t.version}`)
  return USE_MOCK
    ? mockStartFeatureRun(refs)
    : post<FeatureRunResponse>('/packages/feature-comparison', undefined, { params: { refs } })
}

/** run 상태와 결과. 실패도 200 이며 `status=FAILED` · `error_code` 로 구분한다. */
export function fetchFeatureRun(runId: string): Promise<FeatureRunResponse> {
  return USE_MOCK
    ? mockFeatureRun(runId)
    : get<FeatureRunResponse>(`/packages/feature-comparison/${encodeURIComponent(runId)}`)
}
