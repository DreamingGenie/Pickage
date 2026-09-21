/**
 * 인트로 화면 정적 콘텐츠.
 * 기준 문서: docs/Pickage_메뉴구조_IA_0910.md, docs/Pickage_기능별_개발_구상안_0910.md
 *
 * 예시 데이터는 보고서 쪽과 하나를 쓴다 —
 *   생태계 시계열 : @/components/charts/sample
 *   기능 비교표   : @/routes/report/features/sample
 * 인트로가 보여주는 게 실제 화면과 달라지면 그 자체로 과장이 된다.
 */

/** 콜드스타트 진입점. 서비스가 판정하지 않는 값이므로 이유를 붙이지 않는다. */
export const PRESET_PACKAGES: readonly string[] = ['express', 'yaml', 'axios']

export {
  COMPARISON_PACKAGES as EXAMPLE_COMPARISON_PACKAGES,
  FEATURE_ROWS as EXAMPLE_FEATURE_ROWS,
  VERDICT_LABEL,
  type Verdict,
} from '@/routes/report/features/sample'
