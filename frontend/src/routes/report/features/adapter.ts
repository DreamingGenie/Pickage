import type { ChangeSummary, ComparisonView } from '@/routes/report/features/model'

/**
 * 재분석 전후 비교.
 *
 * 응답 변환은 여기 없다 — 결과는 `rag-adapter.ts`(AI 계약), 버전은 개요의
 * `latest_version`(`use-analysis-run.ts`)에서 온다.
 */

/**
 * 재분석 변경점 — 세션이 들고 있는 직전 완료 결과와 방금 끝난 결과를 클라이언트에서 비교한다
 * (구상안 §9.5). 서버는 완료 결과를 남기지 않으므로 새로고침하면 이 비교는 없다.
 *
 * 버전 변경만 다룬다. 결과가 서술형이라(2026-09-22) 문장끼리 비교해 "바뀐 점" 을 뽑지 않는다 —
 * 같은 입력에도 문장은 매번 조금씩 다르게 나온다.
 */
export function diffAnalyses(prev: ComparisonView, next: ComparisonView): ChangeSummary {
  const versionChanges = next.packages.flatMap((pkg) => {
    const before = prev.packages.find((p) => p.name === pkg.name)
    return before && before.version !== pkg.version
      ? [{ name: pkg.name, from: before.version, to: pkg.version }]
      : []
  })
  return { versionChanges }
}

/** 변경점이 하나도 없는지. 같은 버전을 다시 돌렸으면 카드를 띄우지 않는다. */
export function isEmptyChange(change: ChangeSummary): boolean {
  return change.versionChanges.length === 0
}
