import type { PackageEnvItemWire, PackageEnvResponse } from '@/api/types'
import type { ComparisonPackage, EnvironmentRow } from '@/routes/report/features/model'

/**
 * `GET /api/packages/env` 응답을 핵심 비교 요약 표로 접는다 (기능-11-R01).
 *
 * 서버는 **패키지 단위**로 주고 표는 **항목 단위**로 그린다. 그 전치를 여기서 한 번만 하고,
 * 컴포넌트는 `EnvironmentRow[]` 만 본다.
 *
 * <h2>이 표는 AI 비교와 무관하다</h2>
 *
 * 값이 전부 `package_env`(배치가 미리 접어 둔 표)에서 오므로 LLM 을 기다리지 않는다.
 * 그래서 화면에서도 RAG 영역과 분리해 위에 둔다 — 기능-10-R06 의 "완료된 항목 먼저 표시" 다.
 *
 * <h2>없는 값을 지어내지 않는다</h2>
 *
 * 기능-11-R01 의 완료 판단이 "확인된 정보만 표시" 다. 그래서 값이 없으면 `null` 로 두고
 * 표가 `미확인` 으로 적는다 — 0 이나 "없음" 으로 채우면 확인한 결과처럼 읽힌다.
 */

/** 서버가 안 주는 항목은 행을 만들지 않는다 — 빈 행은 "조건이 없다" 로 읽힌다. */
const MODULE_FORMAT_LABEL: Record<string, string> = {
  CJS: 'CommonJS',
  ESM_ONLY: 'ESM 전용',
  // 전수의 21.0% 다. "ESM 이냐 CJS 냐" 로 이분해 적으면 다섯 중 하나가 갈 곳이 없다.
  ESM_CJS: 'ESM · CommonJS 둘 다',
  // unpublish 된 버전이라 선언 자체를 모른다. 미확인으로 적는다.
  UNKNOWN: '',
}

/**
 * 모듈 방식.
 *
 * `UNKNOWN` 은 판정 실패가 아니라 **unpublish 된 버전이라 선언을 못 본 것**이다.
 * 라벨을 붙이면 다섯 번째 형식처럼 보이므로 빈 값으로 두어 `미확인` 으로 내린다.
 */
function moduleFormat(item: PackageEnvItemWire): string | null {
  return MODULE_FORMAT_LABEL[item.module_format] || null
}

/**
 * 타입 선언.
 *
 * **거짓을 "없음" 으로 적지 않는다.** 이 패키지 안에 없다는 뜻이고 `@types/xxx` 를 따로 깔면
 * 된다 — "타입 없음" 으로 적으면 타입스크립트에서 못 쓰는 패키지로 읽힌다.
 */
function typesBundled(item: PackageEnvItemWire): string {
  return item.types_bundled ? '포함' : '별도 설치 필요'
}

/**
 * 개수 표기.
 *
 * `null` 은 0 이 아니라 **모름**이다(unpublish 된 버전은 의존 배열이 통째로 비어 있다).
 * 0 으로 적으면 "의존 없음" 이 되어 거짓이 된다.
 */
function count(value: number | null): string | null {
  return value === null ? null : `${value.toLocaleString()}개`
}

interface RowSpec {
  key: string
  label: string
  value: (item: PackageEnvItemWire) => string | null
}

/**
 * 표에 그릴 항목과 순서.
 *
 * 기능-11-R01 은 "정확한 버전, 실행 조건, 모듈 방식, 타입, 의존 조건" 을 적는데
 * **실행 조건(`engines`)은 수집에 없어 행을 만들지 않는다.** 빈 행을 두면 "조건이 없다" 로
 * 읽히고, 완료 판단이 "확인된 정보만 표시" 라 없는 편이 맞다.
 *
 * 직접 의존과 peer 를 한 행으로 합치지 않는다 — 앞은 깔면 따라오는 것이고 뒤는 사용자가
 * 이미 갖고 있어야 하는 조건이다. 합치면 둘 다 못 읽는다.
 */
const ROWS: RowSpec[] = [
  { key: 'module_format', label: '모듈 방식', value: moduleFormat },
  { key: 'types_bundled', label: '타입 선언', value: typesBundled },
  // 전이 의존이 아니다. 라벨에서 "직접" 을 빼면 실제 설치 규모로 오해된다.
  { key: 'direct_dependencies', label: '직접 의존', value: (i) => count(i.direct_dependencies) },
  { key: 'peer_dependencies', label: 'peer 의존', value: (i) => count(i.peer_dependencies) },
]

/**
 * 비교 대상 순서대로 표를 만든다.
 *
 * 응답의 `items` 순서를 믿지 않고 `packages` 로 다시 맞춘다 — 순서가 어긋나면 값이 옆
 * 패키지 칸에 들어가고, 표는 그게 틀렸다는 것을 보여 주지 못한다.
 *
 * 한 패키지도 못 찾으면 빈 배열이다. 그때 표는 섹션 자체를 그리지 않는다 — 빈 표를 두면
 * 확인한 것이 없다는 사실이 확인 결과처럼 읽힌다.
 */
export function toEnvironmentRows(
  packages: readonly ComparisonPackage[],
  response: PackageEnvResponse | undefined,
): EnvironmentRow[] {
  if (!response || response.items.length === 0) return []

  const byKey = new Map(response.items.map((item) => [`${item.name}@${item.version}`, item]))

  return ROWS.map((spec) => ({
    key: spec.key,
    label: spec.label,
    values: packages.map((pkg) => {
      const item = byKey.get(`${pkg.name}@${pkg.version}`)
      return item ? spec.value(item) : null
    }),
  }))
}

/**
 * 표 아래에 붙는 안내.
 *
 * 못 찾은 대상이 있을 때만 적는다. 그 칸이 `미확인` 인 이유가 "값이 없어서" 가 아니라
 * "그 버전의 자료가 아직 없어서" 라는 것을 알려 준다 — 둘은 사용자가 할 일이 다르다
 * (앞은 기다릴 일이 없고, 뒤는 다른 버전을 고르면 된다).
 */
export function environmentNote(response: PackageEnvResponse | undefined): string | null {
  if (!response || response.not_found.length === 0) return null
  return `${response.not_found.join(', ')} 의 소비 조건 자료가 아직 없습니다.`
}
