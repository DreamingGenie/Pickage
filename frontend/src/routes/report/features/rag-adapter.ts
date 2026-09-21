import type { RagComparisonResult } from '@/api/types'
import type { ComparisonView, FeatureRow } from '@/routes/report/features/model'
import type { Verdict } from '@/routes/report/features/sample'

/**
 * RAG 응답을 화면 모델로 옮긴다.
 *
 * 백엔드는 이 값을 손대지 않고 그대로 통과시킨다 — 계약의 주인이 `ai/rag/main.py` 이고,
 * 옮기면 백엔드의 snake_case 전략이 `featureLabel` 을 `feature_label` 로 바꾼다. 그래서
 * **여기만 camelCase** 이고, 컴포넌트가 쓰는 camelCase 모델로의 변환은 이 파일에서 한 번만 한다.
 *
 * <h2>없는 값을 지어내지 않는다</h2>
 *
 * RAG 는 `dataStatus` 를 두 값(`COMPLETE`·`COMPARISON_LIMITED`)만 내고, 217 이 잡아 둔
 * 여섯 값·`reasonCode` 여섯 종은 주지 않는다. 그 자리를 그럴듯한 값으로 채우면 화면이
 * 확인되지 않은 사유를 확인한 것처럼 적는다 — 셀 단위 상태는 `COMPLETE` 로 두고
 * `reasonCode` 는 비운다. `UNCONFIRMED` 판정 자체가 "확인 범위 표시" 라 그것으로 충분하다.
 *
 * <h2>근거 ID 는 옮기지 않는다</h2>
 *
 * 화면에서 출처 표기와 근거 Drawer 를 뺐다(기획 협의). 응답의 `evidenceIds` 는 서버 계약이라
 * 그대로 오지만 화면 모델에는 싣지 않는다 — 쓰지 않는 값을 들고 다니면 누군가 다시 그린다.
 * `groundedIn` 만 `generalKnowledge` 로 남긴다.
 */
export function toComparisonView(result: RagComparisonResult): ComparisonView {
  const packages = result.packages.map((p) => ({ name: p.package, version: p.version }))

  const rows: FeatureRow[] = result.features.map((feature, index) => ({
    // RAG 는 feature id 를 주지 않는다. 표의 key 로만 쓰이므로 순번으로 만든다.
    id: `f${index}`,
    label: feature.featureLabel,
    cells: feature.results.map((cell) => ({
      packageName: cell.package,
      version: cell.version,
      verdict: cell.verdict as Verdict,
      dataStatus: 'COMPLETE' as const,
      generalKnowledge: cell.groundedIn === 'GENERAL_KNOWLEDGE',
      note: cell.note,
      reasonCode: null,
    })),
  }))

  return {
    packages,
    dataStatus: 'COMPLETE',
    // 억지 표를 만들지 않는다(구상안 §8). RAG 가 비교 가능한 기능이 부족하다고 말하면 그대로 적는다.
    limited: result.dataStatus === 'COMPARISON_LIMITED',
    // 핵심 비교 요약은 이제 이 응답에서 오지 않는다 — `GET /api/packages/env` 가 따로 준다.
    environment: [],
    environmentNote: null,
    rows,
    narrative: result.narrative.map((section) => ({
      heading: section.heading,
      body: section.body,
    })),
    // 표는 있는데 해설만 못 만든 경우. 표의 판정은 그대로 유효하다.
    narrativeError: result.narrativeError,
    analyzedAt: new Date().toISOString(),
    isExample: false,
    // 재시도로 나아질 수 있는 셀이 없다 — RAG 파이프라인에 재시도가 없어서 다시 눌러도
    // 같은 답이 나올 수 있다. 0 이면 화면이 재시도 버튼을 두지 않는다.
    retryableCells: 0,
  }
}

/** 문헌 상태 요약. `LIMITED`·`NONE` 이 섞였으면 판정의 근거가 얇다는 뜻이라 화면에 적는다. */
export function sourceNote(result: RagComparisonResult): string | null {
  const weak = result.sources.filter((s) => s.status === 'LIMITED' || s.status === 'NONE')
  if (weak.length === 0) return null
  const names = weak.map((s) => `${s.package}@${s.version}`).join(', ')
  return `${names} 의 README 가 짧아 판정 근거가 제한적입니다.`
}
