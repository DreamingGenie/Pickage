/**
 * 기능 비교 — 실 API 가 붙기 전에 배포본이 내놓는 유일한 결과 (S15P21A506-217).
 *
 * 분석 서버가 그 자리에서 만든 값이 아니라 구상안 16장의 POC 실측이다. 그래서 **그 세 패키지
 * 조합에 대해서만 참이다.** 다른 조합에는 이 값을 대신 띄우지 않고 "아직 준비되지 않음"
 * 으로 돌려보낸다 — 값이 진짜라는 점이 오히려 오인을 키운다(S15P21A506-328).
 * 응답에 `is_example: true` 를 실어 화면이 예시 딱지를 붙이게 한다.
 *
 * BE 연동(S15P21A506-313)이 끝나면 `endpoints.ts` 가 이 파일 대신 실 endpoint 를 부르고,
 * 이 파일은 지운다.
 *
 * 값의 출처는 `routes/report/features/sample.ts` 하나다. 서비스 소개 페이지와 근거 드로어도
 * 같은 파일을 읽으므로, 여기서 값을 따로 적으면 셋이 어긋난다.
 */

import { ApiError } from '@/api/client'
import {
  FEATURE_NOT_AVAILABLE,
  type FeatureComparisonResponse,
  type FeatureTarget,
  type FeatureVersionsResponse,
} from '@/api/types'
import { COMPARISON_PACKAGES, FEATURE_ROWS } from '@/routes/report/features/sample'

const POC = COMPARISON_PACKAGES.map((entry) => {
  const at = entry.lastIndexOf('@')
  return { name: entry.slice(0, at), version: entry.slice(at + 1) }
})

/** 순서는 보지 않는다 — 같은 셋을 다른 순서로 골라도 POC 가 설명하는 대상은 같다. */
function isPocSelection(names: readonly string[]): boolean {
  if (names.length !== POC.length) return false
  const picked = new Set(names)
  return POC.every((p) => picked.has(p.name))
}

const notAvailable = () =>
  new ApiError(404, FEATURE_NOT_AVAILABLE, '이 조합의 기능 비교는 아직 준비되지 않았습니다.')

export function pocFeatureVersions(names: readonly string[]): Promise<FeatureVersionsResponse> {
  if (!isPocSelection(names)) return Promise.reject(notAvailable())
  return Promise.resolve({
    packages: names.map((name) => {
      const version = POC.find((p) => p.name === name)!.version
      return {
        package_name: name,
        latest_stable: version,
        versions: [{ version, prerelease: false }],
      }
    }),
  })
}

export function pocFeatureComparison(targets: FeatureTarget[]): Promise<FeatureComparisonResponse> {
  const names = targets.map((t) => t.package_name)
  if (!isPocSelection(names)) return Promise.reject(notAvailable())

  // sample.ts 의 셀은 COMPARISON_PACKAGES 순서다. 요청한 순서로 다시 세운다.
  const order = (name: string) => POC.findIndex((p) => p.name === name)
  const evidenceIds = new Set<string>()

  const features = FEATURE_ROWS.map((row, i) => ({
    feature_id: `poc-${i + 1}`,
    feature_label: row.label,
    results: targets.map((target) => {
      const cell = row.cells[order(target.package_name)]
      if (cell.evidenceId) evidenceIds.add(cell.evidenceId)
      return {
        package_name: target.package_name,
        version: target.version,
        verdict: cell.verdict,
        data_status: cell.verdict === 'UNCONFIRMED' ? ('NO_DATA' as const) : ('COMPLETE' as const),
        evidence_ids: cell.evidenceId ? [cell.evidenceId] : [],
        note: cell.note ?? null,
        reason_code: cell.verdict === 'UNCONFIRMED' ? ('SOURCE_ABSENT' as const) : null,
      }
    }),
  }))

  return Promise.resolve({
    data_status: 'COMPLETE',
    comparison_state: 'COMPLETE',
    packages: targets,
    environment: null,
    environment_note: null,
    features,
    narrative: [],
    narrative_error: null,
    evidence_count: evidenceIds.size,
    analyzed_at: '2026-08-31',
    is_example: true,
  })
}
