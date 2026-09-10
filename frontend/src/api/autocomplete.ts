import { useEffect, useMemo, useState } from 'react'

import { useDictManifest, useDictionary, usePackageSearch } from '@/api/queries'

/**
 * 2.3 클라이언트 검색 흐름.
 *
 * ```
 * 입력
 *  → 사전에서 접두사 검색 (메모리, 즉시)
 *  → 결과 5개 이상 : 그대로 표시. 네트워크 요청 없음
 *  → 결과 5개 미만 : 사전 결과를 먼저 표시해두고
 *                    서버 조회(디바운스 200ms) → 도착하면 아래에 이어붙임
 * ```
 *
 * 두 가지를 지켜야 한다.
 * - **사전 결과가 위**다. 사전이 인기순이라 찾는 것이 대개 그 안에 있다.
 * - **사전 로딩이 실패해도 동작한다.** 사전은 최적화이지 의존성이 아니므로,
 *   사전이 없으면 전량 서버 폴백으로 넘어간다.
 */

/** §2.3 — 이 수보다 적게 걸리면 서버에 물어본다. 초기값이며 써보면서 조정한다. */
export const FALLBACK_THRESHOLD = 5

/** §2.3 — 폴백 질의 디바운스. */
export const FALLBACK_DEBOUNCE_MS = 200

/** 화면에 한 번에 띄우는 최대 개수. */
const MAX_SUGGESTIONS = 12

export type SuggestionSource = 'dict' | 'server'

export interface Suggestion {
  name: string
  /** 어디서 왔는지. 화면에서 구분해 표시할 수도 있고 안 할 수도 있다. */
  source: SuggestionSource
}

export interface AutocompleteState {
  suggestions: Suggestion[]
  /** 서버 폴백이 진행 중. 사전 결과는 이미 떠 있으므로 전체 로딩이 아니다. */
  fallbackPending: boolean
  /** 사전을 못 받아 전량 서버 폴백으로 도는 중. 화면에서 굳이 알릴 필요는 없다. */
  dictUnavailable: boolean
}

function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return settled
}

export function usePackageAutocomplete(query: string): AutocompleteState {
  const manifest = useDictManifest()
  const dict = useDictionary(manifest.data?.url)

  const q = query.trim().toLowerCase()

  /**
   * 사전 접두사 검색. 배열 순서가 곧 인기순이라 정렬하지 않고 앞에서부터 채운다.
   * 10만 개를 매 입력마다 훑는 게 걱정될 수 있지만, 필요한 개수를 채우면 멈춘다.
   */
  const dictHits = useMemo(() => {
    const names = dict.data
    if (!q || !names) return []
    const out: string[] = []
    for (const name of names) {
      if (name.toLowerCase().startsWith(q)) {
        out.push(name)
        if (out.length >= MAX_SUGGESTIONS) break
      }
    }
    return out
  }, [dict.data, q])

  const dictUnavailable = manifest.isError || dict.isError

  /**
   * 사전을 아직 받는 중이면 폴백을 켜지 않는다 — 곧 도착할 사전이 답을 갖고 있을 수 있고,
   * 그 사이에 보낸 요청은 대부분 버려진다.
   * 사전이 아예 실패했으면 임계값과 무관하게 서버에 의존한다.
   */
  const dictSettled = dict.isSuccess || dictUnavailable
  const needsFallback = q.length > 0 && dictSettled && dictHits.length < FALLBACK_THRESHOLD

  const debouncedQuery = useDebounced(q, FALLBACK_DEBOUNCE_MS)
  const queryIsSettled = debouncedQuery === q

  const server = usePackageSearch(debouncedQuery, needsFallback && queryIsSettled)

  const suggestions = useMemo(() => {
    const out: Suggestion[] = dictHits.map((name) => ({ name, source: 'dict' }))
    if (!needsFallback) return out

    // 응답이 이전 질의의 것이면 쓰지 않는다. 입력보다 뒤늦게 도착한 결과가 섞이면
    // 목록이 방금 지운 글자에 대한 답을 보여주게 된다.
    const fresh = server.data?.query.toLowerCase() === q ? server.data.items : []

    const seen = new Set(dictHits)
    for (const name of fresh) {
      if (seen.has(name)) continue // 사전과 중복되는 이름은 클라이언트에서 제거한다(§2.3)
      seen.add(name)
      out.push({ name, source: 'server' })
      if (out.length >= MAX_SUGGESTIONS) break
    }
    return out
  }, [dictHits, needsFallback, server.data, q])

  return {
    suggestions,
    fallbackPending: needsFallback && (server.isFetching || !queryIsSettled),
    dictUnavailable,
  }
}
