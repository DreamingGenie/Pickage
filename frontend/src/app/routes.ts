/** 라우트 경로 단일 출처. 링크는 전부 여기를 거친다. */
export const paths = {
  intro: '/',
  analyze: '/analyze',
  candidates: '/analyze/candidates',
  report: (reportId: string) => `/report/${reportId}`,
} as const

/** 03B 근거 드로어를 열어둔 채 리포트로 진입하는 링크 */
export function reportWithEvidence(reportId: string, evidenceId: string) {
  return `${paths.report(reportId)}?evidence=${encodeURIComponent(evidenceId)}`
}
