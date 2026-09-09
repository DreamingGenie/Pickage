import { useQuery } from '@tanstack/react-query'

import {
  fetchDependentsTrend,
  fetchDictManifest,
  fetchDictionary,
  fetchDownloadsTrend,
  fetchPackageSearch,
  fetchPackagesOverview,
  fetchVersionShare,
} from '@/api/endpoints'
import { queryKeys } from '@/api/queries/keys'
import { ApiError } from '@/api/client'
import { MAX_NAMES } from '@/api/types'

export { queryKeys }

/**
 * 400 계열은 재시도해도 같은 결과다. 파라미터가 규칙을 어긴 것이기 때문이다.
 * 500·네트워크만 한 번 더 시도한다.
 */
const retry = (count: number, error: unknown) => {
  if (error instanceof ApiError && error.isValidation) return false
  return count < 1
}

/** 요청 전 상한을 넘겼는지 본다. 넘겼으면 서버가 V002 로 거절하므로 아예 보내지 않는다. */
const usable = (names: readonly string[]) => names.length > 0 && names.length <= MAX_NAMES

/* ------------------------------------------------------------------ *
 * 2.2 사전
 * ------------------------------------------------------------------ */

/**
 * manifest → 사전 파일 순으로 두 번 받는다.
 *
 * 사전은 **최적화이지 의존성이 아니다**(§2.3). 실패해도 화면은 서버 폴백만으로
 * 동작해야 하므로 재시도하지 않고, 에러를 위로 던지지 않는다.
 */
export function useDictManifest() {
  return useQuery({
    queryKey: queryKeys.dict.manifest(),
    queryFn: fetchDictManifest,
    // manifest 는 서버에서 max-age=300 으로 캐시된다. 클라이언트도 같은 감각으로 둔다.
    staleTime: 5 * 60_000,
    retry: false,
  })
}

export function useDictionary(url: string | undefined) {
  return useQuery({
    queryKey: queryKeys.dict.file(url ?? ''),
    queryFn: () => fetchDictionary(url as string),
    enabled: Boolean(url),
    // 내용 해시 URL 이라 같은 URL 의 내용은 절대 바뀌지 않는다.
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
  })
}

/* ------------------------------------------------------------------ *
 * 2.4 검색 폴백
 * ------------------------------------------------------------------ */

/**
 * 서버 폴백 검색.
 *
 * 디바운스는 **호출하는 쪽**이 한다(§2.3, 200ms). 여기서 하면 사전 결과를 먼저
 * 띄우는 타이밍과 엇갈린다.
 */
export function usePackageSearch(q: string, enabled: boolean, limit?: number) {
  return useQuery({
    queryKey: queryKeys.packages.search(q, limit),
    queryFn: () => fetchPackageSearch(q, limit),
    enabled: enabled && q.trim().length > 0,
    // 서버가 1시간 캐시한다(§2.4). 같은 접두사를 두 번 두드려도 다시 안 나간다.
    staleTime: 60 * 60_000,
    retry,
  })
}

/* ------------------------------------------------------------------ *
 * 3·4·5·6
 * ------------------------------------------------------------------ */

export function usePackagesOverview(names: readonly string[]) {
  return useQuery({
    queryKey: queryKeys.packages.overview(names),
    queryFn: () => fetchPackagesOverview(names),
    enabled: usable(names),
    retry,
  })
}

export function useDownloadsTrend(names: readonly string[], from?: string, to?: string) {
  return useQuery({
    queryKey: queryKeys.packages.downloads(names, from, to),
    queryFn: () => fetchDownloadsTrend({ names: [...names], from, to }),
    enabled: usable(names),
    retry,
  })
}

export function useDependentsTrend(names: readonly string[], from?: string, to?: string) {
  return useQuery({
    queryKey: queryKeys.packages.dependents(names, from, to),
    queryFn: () => fetchDependentsTrend({ names: [...names], from, to }),
    enabled: usable(names),
    retry,
  })
}

export function useVersionShare(names: readonly string[], snapshotAt?: string) {
  return useQuery({
    queryKey: queryKeys.packages.versionShare(names, snapshotAt),
    queryFn: () => fetchVersionShare(names, snapshotAt),
    enabled: usable(names),
    retry,
  })
}
