/** 보고서 주소가 비교 대상을 싣는 쿼리 키. 읽는 쪽(`report-page`)과 같은 값을 써야 한다. */
export const REPORT_NAMES_PARAM = 'names'

/**
 * 분석 화면이 기준 패키지를 싣는 쿼리 키. 읽는 쪽(`analyze-selection`)과 같은 값이다.
 *
 * <h2>보고서와 달리 기준을 자리가 아니라 이름으로 싣는다</h2>
 *
 * 보고서의 `?names=a,b,c` 는 **맨 앞이 기준**이라는 약속이 주소 어디에도 적혀 있지 않다.
 * 손으로 재정렬하면 기준이 조용히 바뀌는데 화면에는 그 사실이 드러나지 않는다
 * (S15P21A506-187 이 미해결로 남긴 약점이다). 분석 화면은 그 약속을 물려받지 않는다 —
 * 여기서는 1단계와 2단계를 가르는 것이 "기준이 있느냐" 라서, 기준과 후보를 한 목록에
 * 섞으면 주소만 보고 어느 단계인지 알 수 없다.
 */
export const ANALYZE_BASE_PARAM = 'base'

/** 분석 화면이 **고른 후보**를 싣는 쿼리 키. 구분자는 `names` 와 같은 쉼표다. */
export const ANALYZE_WITH_PARAM = 'with'

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
  /**
   * 분석 화면. 인자 없이 부르면 빈 1단계다.
   *
   * 기준과 후보를 **주소가 들고 있다.** 예전에는 라우터 state 로만 넘겼는데, 브라우저는
   * history state 를 새로고침 뒤에도 남겨서 다른 패키지로 바꿔 검색한 뒤 새로고침하면
   * 처음 넘어온 패키지로 되돌아갔다(S15P21A506-435).
   */
  analyze: (base?: string | null, picked?: readonly string[]) => {
    if (!base) return '/analyze'
    const search = new URLSearchParams({ [ANALYZE_BASE_PARAM]: base })
    if (picked?.length) search.append(ANALYZE_WITH_PARAM, picked.join(','))
    return `/analyze?${search}`
  },
  candidates: '/analyze/candidates',
  report: (reportId: string, names?: readonly string[]) => {
    const base = `/report/${reportId}`
    if (!names?.length) return base
    const search = new URLSearchParams({ [REPORT_NAMES_PARAM]: names.join(',') })
    return `${base}?${search}`
  },
} as const
