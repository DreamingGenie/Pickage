import { useMutation, useQuery } from '@tanstack/react-query'

import {
  fetchCommunityStatus,
  fetchDependentsTrend,
  fetchDictManifest,
  fetchDictionary,
  fetchDownloadsTrend,
  fetchPackageSearch,
  fetchPackagesOverview,
  fetchPdfPreview,
  fetchSimilarPackages,
  fetchRemovalReasons,
  fetchTransitions,
  fetchVersionShare,
  generatePdf,
  postCommunityRefresh,
} from '@/api/endpoints'
import { queryKeys } from '@/api/queries/keys'
import { ApiError } from '@/api/client'
import { MAX_NAMES, type CommunityRefreshTrigger, type TransitionPeriodParam } from '@/api/types'

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
 * 기능-14 보고서 PDF
 * ------------------------------------------------------------------ */

/**
 * 문서 생성.
 *
 * **`useQuery` 가 아니라 `useMutation` 이다.** 조회가 아니라 동작이다 — 누를 때만 일어나야
 * 하고, 화면이 다시 그려졌다고 문서가 또 만들어지면 안 된다.
 *
 * 재시도하지 않는다. 실패하면 사용자가 다시 누르는 것이 맞다. 무거운 작업이라 조용한
 * 재시도는 서버 일을 두 배로 만들면서 화면에는 아무것도 안 보인다.
 */
export function useGeneratePdf() {
  return useMutation({ mutationFn: generatePdf, retry: false })
}

/**
 * 미리보기 HTML.
 *
 * `reportId` 가 있을 때만 받는다 — 모달이 열리기 전에는 보고서가 없다.
 * 같은 보고서는 내용이 절대 바뀌지 않으므로 무한히 캐시한다.
 */
export function usePdfPreview(reportId: string | null) {
  return useQuery({
    queryKey: queryKeys.report.preview(reportId ?? ''),
    queryFn: () => fetchPdfPreview(reportId as string),
    enabled: Boolean(reportId),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
  })
}

/* ------------------------------------------------------------------ *
 * 기능-03 · UC4 유사 패키지
 * ------------------------------------------------------------------ */

/**
 * 기준 패키지의 대체 후보.
 *
 * **`usable()` 을 쓰지 않는다.** 그 검사는 이름 배열의 3개 상한을 보는 것이라 여기와
 * 무관하다. 이름 하나가 비어 있지만 않으면 보낸다.
 *
 * 목록은 **주간 배치가 만든다.** 사용자가 화면을 여닫는 동안 바뀔 일이 없으므로 길게 캐시한다.
 * 모델이 새로 돌면 `model_ver` 가 바뀌는데, 그건 다음 세션에서 반영되면 충분하다.
 */
export function useSimilarPackages(name: string, limit?: number) {
  return useQuery({
    queryKey: queryKeys.packages.similar(name, limit),
    queryFn: () => fetchSimilarPackages(name, limit),
    enabled: name.trim().length > 0,
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

/**
 * 아래 세 조회(`useDownloadsTrend` · `useDependentsTrend` · `useVersionShare`)는
 * **기준일(최신 스냅샷)을 알아야 파라미터가 확정된다.** 그 값은 개요 응답이 알려주므로,
 * 개요보다 먼저 보내면 파라미터가 다른 요청을 한 번 더 보내게 되고 먼저 온 응답은
 * 쓰이지 못한 채 버려진다. 그래서 호출하는 쪽이 `ready` 로 "이제 보내도 된다" 를 넘긴다.
 *
 * 기본값이 `true` 인 이유는 기준일이 필요 없는 호출을 막지 않기 위해서다 —
 * 넘기지 않으면 예전과 똑같이 동작한다.
 */
export function useDownloadsTrend(
  names: readonly string[],
  from?: string,
  to?: string,
  ready = true,
) {
  return useQuery({
    queryKey: queryKeys.packages.downloads(names, from, to),
    queryFn: () => fetchDownloadsTrend({ names: [...names], from, to }),
    enabled: ready && usable(names),
    retry,
  })
}

export function useDependentsTrend(
  names: readonly string[],
  from?: string,
  to?: string,
  ready = true,
) {
  return useQuery({
    queryKey: queryKeys.packages.dependents(names, from, to),
    queryFn: () => fetchDependentsTrend({ names: [...names], from, to }),
    enabled: ready && usable(names),
    retry,
  })
}

export function useVersionShare(names: readonly string[], snapshotAt?: string, ready = true) {
  return useQuery({
    queryKey: queryKeys.packages.versionShare(names, snapshotAt),
    queryFn: () => fetchVersionShare(names, snapshotAt),
    enabled: ready && usable(names),
    retry,
  })
}

/* ------------------------------------------------------------------ *
 * S15P21A506-361·391. 유지·유입·이탈
 *
 * 추이 훅과 달리 다른 조회를 기다리지 않는다 — 기준일이 필요 없고, `period` 자체가
 * 이미 서버가 정한 세 값 중 하나라 개요 응답에 기대는 것이 없다.
 * ------------------------------------------------------------------ */

export function useTransitions(
  names: readonly string[],
  period: TransitionPeriodParam,
  ready = true,
) {
  return useQuery({
    queryKey: queryKeys.packages.transitions(names, period),
    queryFn: () => fetchTransitions(names, period),
    enabled: ready && usable(names),
    retry,
  })
}

/**
 * 이탈 사유 (S15P21A506-396·410). 위와 **같은 `period` 값을 받는다** — 프리셋도
 * 기본값도 기준일도 같아서, 화면이 선택기 하나를 두 패널에 공유한다.
 * 별도 쿼리인 이유는 단위가 다르고(패키지 수 vs 전이 건수) 서버 엔드포인트가 갈려서다 —
 * 한쪽이 느리거나 실패해도 다른 쪽 패널은 그대로 뜬다.
 */
export function useRemovalReasons(
  names: readonly string[],
  period: TransitionPeriodParam,
  ready = true,
) {
  return useQuery({
    queryKey: queryKeys.packages.removalReasons(names, period),
    queryFn: () => fetchRemovalReasons(names, period),
    enabled: ready && usable(names),
    retry,
  })
}

/* ------------------------------------------------------------------ *
 * S15P21A506-316. GitHub 커뮤니티 현황
 * ------------------------------------------------------------------ */

/**
 * 잡 상태 조회다 — 재마운트마다 새로 받아야 하므로 `staleTime: 0`.
 * `refetchInterval` 은 마지막으로 받은 응답이 QUEUED/RUNNING 일 때만 서버가 알려준
 * `poll_after_seconds` 간격으로 다시 부른다(그 외엔 폴링을 끈다) — 문서 §8.2·8.3.
 *
 * `enabled` 는 호출부(`community-report-tab.tsx`)가 "탭이 실제로 보이는가"를 판단해
 * 넘긴다. 언마운트가 아니라 이 값으로 폴링을 끄는 이유는 report-page 가 탭을
 * 마운트 보존하기 때문이다(생태계 필터 유지) — 언마운트를 기대할 수 없다.
 */
export function useCommunityStatus(name: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.community.status(name),
    queryFn: ({ signal }) => fetchCommunityStatus(name, signal),
    enabled: enabled && name.trim().length > 0,
    staleTime: 0,
    refetchInterval: (query) => {
      const status = query.state.data?.refresh?.status
      if (status !== 'QUEUED' && status !== 'RUNNING') return false
      return (query.state.data?.refresh?.poll_after_seconds ?? 2) * 1000
    },
    refetchIntervalInBackground: false,
    retry: (count, error) => {
      if (count >= 2) return false
      // V*(형식 오류)·C006(패키지 없음)·호출자 취소는 다시 해도 같은 결과다.
      // 그 외(네트워크·타임아웃·5xx)만 최대 2회 재시도한다(§8.1).
      if (error instanceof ApiError) return !error.isValidation && error.code !== 'C006'
      return false
    },
  })
}

/** 조회가 아니라 동작이다 — POST 는 자동 재시도하지 않는다(§8.1). */
export function useCommunityRefresh() {
  return useMutation({
    mutationFn: ({ name, trigger }: { name: string; trigger: CommunityRefreshTrigger }) =>
      postCommunityRefresh(name, trigger),
    retry: false,
  })
}
