/**
 * 최근에 연 비교 조합 — 이 브라우저에만 남는 편의 기능이다.
 *
 * 인트로의 "최근 본 조합" 이 읽고, 보고서 화면이 열릴 때 쓴다. 서버에 저장하지 않으므로
 * 다른 기기·다른 사람과 공유되지 않는다. 사생활 모드나 저장소가 막힌 브라우저에서는
 * 읽기·쓰기가 예외를 던질 수 있어 모두 삼키고 빈 목록으로 둔다 — 없어도 화면이 온전해야 한다.
 */
const KEY = 'pickage:recent-comparisons'
export const MAX_RECENT = 3

function isNames(v: unknown): v is string[] {
  return Array.isArray(v) && v.length > 0 && v.every((x) => typeof x === 'string' && x.length > 0)
}

export function readRecentComparisons(): string[][] {
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter(isNames).slice(0, MAX_RECENT) : []
  } catch {
    return []
  }
}

/** 맨 앞에 넣고, 같은 조합(순서까지 같은 것)은 한 번만 둔다. 한 개짜리는 비교가 아니라 남기지 않는다. */
export function rememberComparison(names: readonly string[]): void {
  if (names.length < 2) return
  try {
    const key = names.join(',')
    const next = [[...names], ...readRecentComparisons().filter((n) => n.join(',') !== key)].slice(
      0,
      MAX_RECENT,
    )
    window.localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // 저장소를 못 쓰면 기억하지 않을 뿐이다.
  }
}
