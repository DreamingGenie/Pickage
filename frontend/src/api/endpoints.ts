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
  mockVersionShare,
} from '@/api/mock/handlers'
import type {
  DependentsTrendResponse,
  DictManifest,
  DownloadsTrendResponse,
  PackageDictionary,
  PackageSearchResponse,
  PackagesOverviewResponse,
  PdfGenerateRequest,
  PdfJob,
  SimilarPackagesResponse,
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
