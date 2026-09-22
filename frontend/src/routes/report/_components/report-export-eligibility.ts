import type { AnalysisRun } from '@/routes/report/_components/use-analysis-run'

/**
 * 보고서 내보내기(PDF·HAND-OFF)의 자격 조건 — 구상안 §13.2.
 *
 * <p>원래 `pdf-export-dialog.tsx` 안에 있었다. `report-page.tsx`의 `pdfReady`가 "PDF 내보내기
 * 창의 BLOCKED 조건과 같다"는 주석만 남긴 채 같은 로직을 손으로 다시 적고 있었는데
 * (S15P21A506-467에서 HAND-OFF 버튼이 같은 조건을 또 필요로 하면서 이 중복이 셋으로 늘어날
 * 뻔했다) — 그래서 한 곳으로 뺐다. PDF 모달, 헤더의 `pdfReady`, HAND-OFF 버튼 전부 이 함수
 * 하나를 부른다.
 *
 * <h2>`BLOCKED` 사유는 아직 둘뿐이다</h2>
 *
 * 구상안 §13.2 의 차단 사유 다섯 중 클라이언트에서 지금 실제로 판단 가능한 건
 * `FEATURE_ANALYSIS_REQUIRED`(기능 비교 미실행)·`VERSION_RESULT_MISMATCH`(재분석 중,
 * `ANALYSIS_RUNNING`과 겹쳐 판단)뿐이다. 나머지 셋(`COMPARISON_NOT_CONFIRMED`·
 * `ECOSYSTEM_RESULT_INCOMPLETE`·`SNAPSHOT_CREATION_ERROR`)은 타입에는 있지만 판단할
 * 신호가 아직 없어 항상 통과시킨다 — 신호가 생기면 이 함수 안의 조건만 채운다.
 */
export type BlockReason =
  | 'COMPARISON_NOT_CONFIRMED'
  | 'ECOSYSTEM_RESULT_INCOMPLETE'
  | 'SNAPSHOT_CREATION_ERROR'
  | 'FEATURE_ANALYSIS_REQUIRED'
  | 'VERSION_RESULT_MISMATCH'

export const BLOCK_REASON_LABEL: Record<BlockReason, string> = {
  COMPARISON_NOT_CONFIRMED: '비교 대상이 아직 확정되지 않았습니다.',
  ECOSYSTEM_RESULT_INCOMPLETE: '생태계 분석 결과가 아직 준비되지 않았습니다.',
  SNAPSHOT_CREATION_ERROR: '보고서 사본을 만드는 중 오류가 발생했습니다.',
  FEATURE_ANALYSIS_REQUIRED: '기능 비교 분석이 아직 실행되지 않았습니다.',
  VERSION_RESULT_MISMATCH:
    '기능 비교가 실행 중이거나, 선택한 버전으로 재분석이 필요합니다. 재분석이 끝난 뒤 다시 시도해 주세요.',
}

/**
 * 지금 실제로 판단 가능한 두 사유만 채운다. 나머지 셋은 신호가 없어 늘 통과한다 —
 * 자세한 사유는 이 파일 상단 주석 참고.
 */
export function reportExportBlockReasons(run: AnalysisRun): BlockReason[] {
  if (!run.hasCompletedOnce) return ['FEATURE_ANALYSIS_REQUIRED']
  // 진행 중이거나, 선택한 버전이 완료 결과와 달라 재분석이 필요하면 막는다(구상안 §9.2·§13.2).
  // 기존 결과는 화면에 남아 있어도 "현재 선택 버전의 결과"가 아니다.
  if (run.status === 'RUNNING' || run.reanalysisRequired) return ['VERSION_RESULT_MISMATCH']
  return []
}

/** 보고서(PDF·HAND-OFF)를 지금 만들 수 있는지. `reportExportBlockReasons(run).length === 0`. */
export function reportExportReady(run: AnalysisRun): boolean {
  return reportExportBlockReasons(run).length === 0
}
