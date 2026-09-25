/**
 * 인트로 화면 정적 콘텐츠.
 * 현재 설계 근거: docs/Pickage_메뉴구조_IA_0923.md,
 * docs/Pickage_기능별_개발_구상안_0923.md
 *
 * 인트로의 예시 그래프는 보고서 쪽 표본(@/components/charts/sample)을 그대로 쓴다.
 * 예전의 "분석 결과 예시"(생태계 화면 + 기능 판정표)는 걷어냈다 — 기능 비교 화면이 스펙 표 +
 * AI 요약으로 바뀌면서 예시가 실제 화면과 달라졌고, 예시 조합을 누르면 진짜 보고서가 열리므로
 * 인트로가 보고서를 흉내 낼 이유가 없어졌다.
 */

/** 콜드스타트 진입점. 서비스가 판정하지 않는 값이므로 이유를 붙이지 않는다. */
export const PRESET_PACKAGES: readonly string[] = ['express', 'yaml', 'axios']

/**
 * 첫 방문자용 예시 조합. 누르면 후보 고르기를 건너뛰고 보고서로 바로 간다.
 * 이름은 쓰임새(라벨)로만 묶는다 — 조합 안에서 어느 쪽이 낫다는 뜻을 담지 않는다(IA 1-12).
 * 기준 패키지는 맨 앞이다(보고서의 비교 순서 = 배열 순서).
 */
export const PRESET_COMBOS: readonly { label: string; names: readonly string[] }[] = [
  { label: '로그 남기기', names: ['winston', 'pino', 'bunyan'] },
  { label: '웹 서버', names: ['express', 'koa', 'fastify'] },
  { label: 'HTTP 요청', names: ['axios', 'got', 'ky'] },
]
