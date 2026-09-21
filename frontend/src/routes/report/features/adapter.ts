import type { ChangeSummary, ComparisonView } from '@/routes/report/features/model'

/**
 * 재분석 전후 비교.
 *
 * 응답 변환은 여기 없다 — 판정표는 `rag-adapter.ts`(AI 계약), 버전은 개요의
 * `latest_version`(`use-analysis-run.ts`)에서 온다.
 */

/**
 * 재분석 변경점 — 세션이 들고 있는 직전 완료 결과와 방금 끝난 결과를 클라이언트에서 비교한다
 * (구상안 §9.5). 서버는 완료 결과를 남기지 않으므로 새로고침하면 이 비교는 없다.
 *
 * 다루는 것: 버전 변경 · 같은 이름의 기능의 판정 변경. 출처 증감은 세지 않는다 — 근거 ID 에
 * 버전이 들어 있어 버전을 바꾸면 전부 "바뀐 것" 으로 잡힌다.
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
    // 순번이 아니라 **기능 이름**으로 짝짓는다. RAG 는 비교 축을 매번 새로 정해서, 같은 순번이
    // 다른 기능일 수 있다. 이름이 조금이라도 다르면 비교하지 않는다 — 틀린 비교보다 덜 말하는 편이 낫다.
    const before = prev.rows.find((r) => r.label === row.label)
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

  return { versionChanges, verdictChanges }
}

/** 변경점이 하나도 없는지. 같은 버전을 다시 돌렸는데 결과가 같으면 카드를 띄우지 않는다. */
export function isEmptyChange(change: ChangeSummary): boolean {
  return change.versionChanges.length === 0 && change.verdictChanges.length === 0
}
