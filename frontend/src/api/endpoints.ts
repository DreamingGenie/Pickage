/**
 * 엔드포인트 한 겹.
 *
 * **분기는 여기 한 곳에서만 일어난다.** 화면과 쿼리 훅은 mock 여부를 모른다 —
 * 알게 되면 서버를 붙일 때 화면 코드까지 손봐야 하고, mock 에서만 되는 동작이
 * 조용히 화면에 스며든다.
 *
 * 켜기: `.env.local` 에 `VITE_USE_MOCK=true`
 */

import { get, getRaw } from '@/api/client'
import {
  mockDependentsTrend,
  mockDictManifest,
  mockDictionary,
  mockDownloadsTrend,
  mockPackagesOverview,
  mockSearch,
  mockVersionShare,
} from '@/api/mock/handlers'
import type {
  DependentsTrendResponse,
  DictManifest,
  DownloadsTrendResponse,
  PackageDictionary,
  PackageSearchResponse,
  PackagesOverviewResponse,
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
