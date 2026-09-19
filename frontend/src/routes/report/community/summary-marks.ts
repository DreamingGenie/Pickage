import type { CommunitySummaryMark } from '@/api/types'

/**
 * 요약문을 강조 구간(`summary_marks`)대로 나눈 한 조각(S15P21A506-409).
 * 핵심어(`term`)는 굵게, 핵심 문장(`sentence`)은 형광펜으로 그린다. 핵심 문장 안에 든 핵심어는 둘 다 켜진다.
 */
export interface SummarySegment {
  text: string
  term: boolean
  sentence: boolean
}

/**
 * 서버가 준 구간이 이 요약문에 쓸 수 있는가. 구간은 서버가 계산한 UTF-16 오프셋 `[start, end)` 이고 JS 문자열과 같은 단위다.
 * 요약문이 바뀌었는데 구간이 옛것이거나 값이 이상하면 **그 구간만 버린다** — 강조는 읽기 보조라 없어도 글은 그대로 읽혀야 한다.
 */
function usable(text: string, mark: CommunitySummaryMark): boolean {
  return (
    Number.isInteger(mark.start) &&
    Number.isInteger(mark.end) &&
    mark.start >= 0 &&
    mark.start < mark.end &&
    mark.end <= text.length &&
    (mark.kind === 'KEY_TERM' || mark.kind === 'KEY_SENTENCE') &&
    // 공백뿐인 구간에 강조를 그리지 않는다
    text.slice(mark.start, mark.end).trim() !== ''
  )
}

/**
 * 요약문을 경계별로 잘라 조각마다 어떤 강조가 켜지는지 계산한다. 같은 종류끼리 겹쳐도(서버가 막지만) 화면이 깨지지 않게 경계
 * 방식으로 푼다 — 조각을 이어 붙이면 언제나 원문과 같다.
 */
export function segmentSummary(
  text: string,
  marks: readonly CommunitySummaryMark[] | null | undefined,
): SummarySegment[] {
  if (text === '') return []
  const valid = (marks ?? []).filter((m) => usable(text, m))
  if (valid.length === 0) return [{ text, term: false, sentence: false }]

  const cuts = new Set<number>([0, text.length])
  for (const m of valid) {
    cuts.add(m.start)
    cuts.add(m.end)
  }
  const points = [...cuts].sort((a, b) => a - b)

  const segments: SummarySegment[] = []
  for (let i = 0; i < points.length - 1; i++) {
    const from = points[i]
    const to = points[i + 1]
    const covers = (kind: CommunitySummaryMark['kind']) =>
      valid.some((m) => m.kind === kind && m.start <= from && to <= m.end)
    segments.push({
      text: text.slice(from, to),
      term: covers('KEY_TERM'),
      sentence: covers('KEY_SENTENCE'),
    })
  }
  return segments
}

/**
 * 저장소 이름은 서버가 검증한 `owner/name` 이지만, 주소를 만드는 곳이라 한 번 더 모양을 본다.
 * GitHub 만 지원하므로(다른 호스트는 서버가 `UNSUPPORTED_HOST` 로 막는다) 호스트는 고정이다.
 */
const FULL_NAME = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/

/** Issue 의 GitHub 페이지 주소. 저장소 이름이나 번호가 이상하면 null — 그때는 링크를 그리지 않는다. */
export function githubIssueUrl(
  fullName: string | null | undefined,
  issueNumber: number,
): string | null {
  if (!fullName || !FULL_NAME.test(fullName)) return null
  if (!Number.isInteger(issueNumber) || issueNumber <= 0) return null
  return `https://github.com/${fullName}/issues/${issueNumber}`
}
