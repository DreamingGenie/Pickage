import type {
  FeatureCellWire,
  FeatureComparisonResponse,
  FeatureVersionsResponse,
} from '@/api/types'
import {
  MIN_FEATURES,
  RETRYABLE_REASONS,
  type ChangeSummary,
  type ComparisonView,
  type FeatureCell,
  type PackageVersions,
} from '@/routes/report/features/model'

/**
 * 서버 응답 → 화면 모델. snake_case → camelCase 변환은 여기서만 한다.
 * 근거 없는 값을 채워 넣지 않는다 — 없으면 없는 채로 둔다.
 */

export function adaptVersions(response: FeatureVersionsResponse): PackageVersions[] {
  return response.packages.map((p) => ({
    name: p.package_name,
    latestStable: p.latest_stable,
    choices: p.versions.map((v) => ({ version: v.version, prerelease: v.prerelease })),
  }))
}

function adaptCell(wire: FeatureCellWire): FeatureCell {
  return {
    packageName: wire.package_name,
    version: wire.version,
    verdict: wire.verdict,
    dataStatus: wire.data_status,
    evidenceIds: wire.evidence_ids,
    note: wire.note,
    reasonCode: wire.reason_code,
  }
}

export function adaptComparison(response: FeatureComparisonResponse): ComparisonView {
  const packages = response.packages.map((p) => ({ name: p.package_name, version: p.version }))

  const rows = response.features.map((row) => ({
    id: row.feature_id,
    label: row.feature_label,
    cells: row.results.map(adaptCell),
  }))

  // 열 순서는 packages 를 따른다. 응답이 패키지 이름으로 값을 실어 주므로 이름으로 찾는다.
  const environment = (response.environment ?? []).map((row) => ({
    key: row.key,
    label: row.label,
    values: packages.map(
      (pkg) => row.values.find((v) => v.package_name === pkg.name)?.value ?? null,
    ),
  }))

  const evidenceIds = new Set<string>()
  let retryableCells = 0
  for (const row of rows) {
    for (const cell of row.cells) {
      cell.evidenceIds.forEach((id) => evidenceIds.add(`${cell.packageName}:${id}`))
      if (cell.reasonCode && RETRYABLE_REASONS.has(cell.reasonCode)) retryableCells += 1
    }
  }

  return {
    packages,
    dataStatus: response.data_status,
    limited: response.comparison_state === 'COMPARISON_LIMITED' || rows.length < MIN_FEATURES,
    environment,
    environmentNote: response.environment_note,
    rows,
    narrative: response.narrative.map((n) => ({
      heading: n.heading,
      body: n.body,
      evidenceIds: n.evidence_ids,
    })),
    narrativeError: response.narrative_error,
    evidenceCount: response.evidence_count ?? evidenceIds.size,
    analyzedAt: response.analyzed_at,
    isExample: response.is_example === true,
    retryableCells,
  }
}

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
