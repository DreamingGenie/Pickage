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
 * <h2>기능 비교는 선행 조건이 아니다 (2026-09-22)</h2>
 *
 * 예전에는 기능 비교를 한 번도 안 돌렸거나 재분석이 필요하면 PDF·HAND-OFF 자체를 막았다.
 * 이제는 막지 않는다 — 생태계·커뮤니티만으로도 보고서를 만들 수 있고, 기능 비교 구역은
 * {@link featuresExportable} 가 참일 때만 체크리스트에서 고를 수 있다.
 *
 * 구상안 §13.2 의 남은 차단 사유 셋(`COMPARISON_NOT_CONFIRMED`·`ECOSYSTEM_RESULT_INCOMPLETE`·
 * `SNAPSHOT_CREATION_ERROR`)은 판단할 신호가 아직 없어 늘 통과시킨다 — 신호가 생기면
 * {@link reportExportBlockReasons} 안의 조건만 채운다.
 */
export type BlockReason =
  'COMPARISON_NOT_CONFIRMED' | 'ECOSYSTEM_RESULT_INCOMPLETE' | 'SNAPSHOT_CREATION_ERROR'

export const BLOCK_REASON_LABEL: Record<BlockReason, string> = {
  COMPARISON_NOT_CONFIRMED: '비교 대상이 아직 확정되지 않았습니다.',
  ECOSYSTEM_RESULT_INCOMPLETE: '생태계 분석 결과가 아직 준비되지 않았습니다.',
  SNAPSHOT_CREATION_ERROR: '보고서 사본을 만드는 중 오류가 발생했습니다.',
}

/** 지금은 판단할 신호가 있는 차단 사유가 없다 — 늘 빈 목록이다. 자세한 사유는 이 파일 상단 주석 참고. */
export function reportExportBlockReasons(_run: AnalysisRun): BlockReason[] {
  return []
}

/**
 * 기능 비교 결과를 보고서에 실을 수 있는지. 완료 결과가 있고, 지금 고른 버전의 결과여야 한다 —
 * 분석 중이거나 버전을 바꿔 재분석이 필요하면 화면의 결과는 "지금 고른 버전"의 것이 아니다
 * (구상안 §9.2).
 */
export function featuresExportable(run: AnalysisRun): boolean {
  return (
    run.hasCompletedOnce &&
    run.rawResult !== null &&
    run.status !== 'RUNNING' &&
    !run.reanalysisRequired
  )
}

/** 보고서(PDF·HAND-OFF)를 지금 만들 수 있는지. `reportExportBlockReasons(run).length === 0`. */
export function reportExportReady(run: AnalysisRun): boolean {
  return reportExportBlockReasons(run).length === 0
}
