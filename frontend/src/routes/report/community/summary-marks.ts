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
