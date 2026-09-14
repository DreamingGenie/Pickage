/** 보고서 주소가 비교 대상을 싣는 쿼리 키. 읽는 쪽(`report-page`)과 같은 값을 써야 한다. */
export const REPORT_NAMES_PARAM = 'names'

/**
 * 라우트 경로 단일 출처.
 *
 * <h2>비교 대상은 경로가 아니라 쿼리에 싣는다</h2>
 *
 * 예전에는 라우터 state 로만 넘겼다. 그러면 **링크가 보고서를 가리키지 못한다** —
 * 받는 사람에게는 state 가 없어 화면이 조용히 기본 조합으로 떨어지고, 보낸 사람과
 * 다른 보고서를 보면서도 그 사실을 알 방법이 없다.
 *
 * 구분자는 쉼표다. API 의 `names` 와 같은 형태라 주소만 보고 어떤 요청이 나갈지 읽을 수
 * 있고(명세 0.1), npm 이름에는 쉼표가 들어갈 수 없어 구분자와 충돌하지 않는다.
 *
 * `reportId` 는 남겨 둔다. 지금은 언제나 `draft` 지만, 서버가 컨텍스트 id 를 발급하게
 * 되면 그 자리가 여기다(S15P21A506-187). 경로 모양을 지금 바꾸면 커뮤니티 탭이 소유한
 * 공통 route 작업(S15P21A506-316)과 겹친다.
 */
export const paths = {
  intro: '/',
  analyze: '/analyze',
  candidates: '/analyze/candidates',
  report: (reportId: string, names?: readonly string[]) => {
    const base = `/report/${reportId}`
    if (!names?.length) return base
    const search = new URLSearchParams({ [REPORT_NAMES_PARAM]: names.join(',') })
    return `${base}?${search}`
  },
} as const

/**
 * 03B 근거 드로어를 열어둔 채 리포트로 진입하는 링크.
 *
 * 비교 대상을 함께 받는다. 빠뜨리면 드로어는 열리는데 보고서가 비는 주소가 된다.
 */
export function reportWithEvidence(
  reportId: string,
  evidenceId: string,
  names?: readonly string[],
) {
  const url = paths.report(reportId, names)
  return `${url}${url.includes('?') ? '&' : '?'}evidence=${encodeURIComponent(evidenceId)}`
}
