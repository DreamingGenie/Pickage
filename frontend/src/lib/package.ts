import type { PackageRef } from '@/api/types'

export type ParseResult = { ok: true; value: PackageRef } | { ok: false; reason: string }

/** npm 패키지명 규칙(스코프 포함)의 최소 검증 */
const NAME_RE = /^(?:@[a-z0-9-*~][a-z0-9-*._~]*\/)?[a-z0-9-~][a-z0-9-._~]*$/

/** "name" 또는 "name@range" 를 PackageRef 로 파싱한다. */
export function parsePackageInput(raw: string): ParseResult {
  const input = raw.trim()
  if (!input) return { ok: false, reason: '패키지명을 입력하세요.' }

  const at = input.lastIndexOf('@')
  const hasRange = at > 0
  const name = hasRange ? input.slice(0, at) : input
  const range = hasRange ? input.slice(at + 1).trim() : null

  if (!NAME_RE.test(name)) {
    return { ok: false, reason: '올바른 npm 패키지명이 아닙니다.' }
  }
  if (hasRange && !range) {
    return { ok: false, reason: '버전 레인지가 비어 있습니다.' }
  }

  return { ok: true, value: { name, range } }
}
