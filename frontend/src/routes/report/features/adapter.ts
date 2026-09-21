import type { ChangeSummary, ComparisonView } from '@/routes/report/features/model'

/**
 * 재분석 전후 비교.
 *
 * 응답 변환은 여기 없다 — 판정표는 `rag-adapter.ts`(AI 계약), 버전은 개요의
 * `latest_version`(`use-analysis-run.ts`)에서 온다.
 */

/** 근거를 패키지와 묶어 센다 — 같은 ID 가 다른 패키지에 있으면 다른 근거다. */
const evidenceKeys = (view: ComparisonView): Set<string> => {
  const keys = new Set<string>()
  for (const row of view.rows) {
    for (const cell of row.cells) {
      cell.evidenceIds.forEach((id) => keys.add(`${cell.packageName}:${id}`))
    }
  }
  return keys
}

/**
 * 재분석 변경점 — 세션이 들고 있는 직전 완료 결과와 방금 끝난 결과를 클라이언트에서 비교한다
 * (구상안 §9.5). 서버는 완료 결과를 남기지 않으므로 새로고침하면 이 비교는 없다.
 *
 * 다루는 것: 버전 변경 · verdict 변경 · 근거 추가/제거. analyzer/ruleset 버전은 응답에
 * 아직 없어 다루지 않는다.
 */
export function diffAnalyses(prev: ComparisonView, next: ComparisonView): ChangeSummary {
  const versionChanges = next.packages.flatMap((pkg) => {
    const before = prev.packages.find((p) => p.name === pkg.name)
    return before && before.version !== pkg.version
      ? [{ name: pkg.name, from: before.version, to: pkg.version }]
      : []
  })

  const verdictChanges: ChangeSummary['verdictChanges'] = []
  for (const row of next.rows) {
    const before = prev.rows.find((r) => r.id === row.id)
    if (!before) continue
    for (const cell of row.cells) {
      const old = before.cells.find((c) => c.packageName === cell.packageName)
      if (old && old.verdict !== cell.verdict) {
        verdictChanges.push({
          feature: row.label,
          name: cell.packageName,
          from: old.verdict,
          to: cell.verdict,
        })
      }
    }
  }

  const before = evidenceKeys(prev)
  const after = evidenceKeys(next)
  return {
    versionChanges,
    verdictChanges,
    evidenceAdded: [...after].filter((k) => !before.has(k)).length,
    evidenceRemoved: [...before].filter((k) => !after.has(k)).length,
  }
}

/** 변경점이 하나도 없는지. 같은 버전을 다시 돌렸는데 결과가 같으면 카드를 띄우지 않는다. */
export function isEmptyChange(change: ChangeSummary): boolean {
  return (
    change.versionChanges.length === 0 &&
    change.verdictChanges.length === 0 &&
    change.evidenceAdded === 0 &&
    change.evidenceRemoved === 0
  )
}
