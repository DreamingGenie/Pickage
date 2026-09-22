import type { PdfFeaturesPayload, RagComparisonResult } from '@/api/types'
import type { ComparisonView } from '@/routes/report/features/model'

/**
 * RAG 응답을 화면 모델로 옮긴다.
 *
 * 백엔드는 이 값을 손대지 않고 그대로 통과시킨다 — 계약의 주인이 `ai/rag/main.py` 이고,
 * 옮기면 백엔드의 snake_case 전략이 키 이름을 바꾼다. 그래서 **여기만 camelCase** 이고,
 * 컴포넌트가 쓰는 모델로의 변환은 이 파일에서 한 번만 한다.
 *
 * 2026-09-22 판정표를 없애고 공통점·패키지별 차이점 서술만 받는다.
 */
export function toComparisonView(result: RagComparisonResult): ComparisonView {
  const bodyOf = new Map(result.differences.map((d) => [d.package, d.body]))
  const packages = result.packages.map((p) => ({ name: p.package, version: p.version }))
  return {
    packages,
    // 억지 서술을 만들지 않는다. RAG 가 자료가 부족하다고 말하면 그대로 적는다.
    limited: result.dataStatus === 'COMPARISON_LIMITED',
    common: result.common,
    // 요청한 패키지 순서로 세운다. 서버가 패키지마다 한 문단을 보장하지만(verify_result),
    // 빠졌으면 빈 문단으로 두고 화면이 그 사실을 적는다.
    differences: packages.map((p) => ({ ...p, body: bodyOf.get(p.name) ?? '' })),
    analyzedAt: new Date().toISOString(),
  }
}

/**
 * PDF·Markdown 요청 payload 로 옮긴다(구상안 §13.1·§14.5, S15P21A506-463).
 * 백엔드 계약(snake_case)이라 {@link toComparisonView} 와 따로 둔다.
 */
export function toFeaturesPdfPayload(result: RagComparisonResult): PdfFeaturesPayload {
  return {
    packages: result.packages.map((p) => ({ package_name: p.package, version: p.version })),
    common: result.common,
    differences: result.differences.map((d) => ({
      package_name: d.package,
      version: d.version,
      body: d.body,
    })),
    limited: result.dataStatus === 'COMPARISON_LIMITED',
  }
}

/** 문헌 상태 요약. `LIMITED`·`NONE` 이 섞였으면 서술의 근거가 얇다는 뜻이라 화면에 적는다. */
export function sourceNote(result: RagComparisonResult): string | null {
  const weak = result.sources.filter((s) => s.status === 'LIMITED' || s.status === 'NONE')
  if (weak.length === 0) return null
  const names = weak.map((s) => `${s.package}@${s.version}`).join(', ')
  return `${names} 의 README 가 짧아 설명이 제한적일 수 있어요.`
}
