import { useMemo } from 'react'
import { useLocation } from 'react-router'

/**
 * 기준 패키지(S15P21A506-316). `analyze-page.tsx`가 router state 로 명시해 넘긴다.
 *
 * **없으면 `packages[0]`으로 대체한다** — 새로고침·공유 링크는 state 를 잃으므로
 * 이 호환이 없으면 커뮤니티 탭이 매번 "문맥 없음"이 된다. 반대로 **명시된 값이
 * `packages[0]`과 다르면 임의로 고치지 않고 충돌로 표시**한다 — 조용히 고치면
 * 사용자가 고른 기준과 다른 저장소를 보여주게 된다(구현계획 §8.1).
 */
export function useReportBasePackage(packages: readonly string[]): {
  basePackage: string | null
  conflict: boolean
} {
  const location = useLocation()
  return useMemo(() => {
    const explicit = (location.state as { basePackage?: string } | null)?.basePackage
    if (!explicit) return { basePackage: packages[0] ?? null, conflict: false }
    if (packages[0] !== explicit) return { basePackage: null, conflict: true }
    return { basePackage: explicit, conflict: false }
  }, [location.state, packages])
}
