import { useMemo } from 'react'

import { MAX_NAMES } from '@/api/types'
import { parsePackageInput } from '@/lib/package'

/** 기준 패키지를 포함한 비교 대상 수(IA §1-3). 서버의 `names` 상한과 같은 값이다. */
export const MAX_COMPARISON = MAX_NAMES

/** 기준을 뺀, 후보로 채울 수 있는 자리 수. */
export const MAX_PICKED = MAX_COMPARISON - 1

/** 주소에서 읽어낸 분석 화면의 선택. */
export interface AnalyzeSelection {
  /** 확인을 요청할 기준 패키지. 없거나 형식이 아니면 `null` 이고 화면은 1단계로 열린다. */
  base: string | null
  /** 함께 비교하려고 고른 후보. 기준과 겹치지 않고 상한까지만 남는다. */
  picked: string[]
  /** 자리가 모자라 뺀 후보. */
  dropped: string[]
  /** npm 이름 형식이 아니어서 뺀 것. 기준이 여기 들어가면 `base` 는 `null` 이다. */
  rejected: string[]
}

const EMPTY: AnalyzeSelection = { base: null, picked: [], dropped: [], rejected: [] }

/**
 * 한 이름을 조회에 쓸 형태로 고친다. 형식이 아니면 `null`.
 *
 * **버전 레인지는 떼어낸다**(`lodash@^4` → `lodash`). 서버의 이름 규칙에는 `@` 와 `^` 가
 * 없어서 붙은 채로 보내면 V004 로 거절당한다. 이 화면은 버전이 아니라 패키지를 비교하므로
 * (정확 버전 결합은 S15P21A506-183 · S15P21A506-313) 떼는 것이 사용자의 뜻에 가깝다.
 */
function normalize(raw: string): string | null {
  const parsed = parsePackageInput(raw)
  return parsed.ok ? parsed.value.name : null
}

/**
 * 분석 화면의 선택을 주소에서 읽는다 (`?base=lodash&with=dayjs,luxon`).
 *
 * <h2>보내기 전에 걸러내는 이유</h2>
 *
 * 주소는 **사용자가 친 것이 아닐 수 있다.** 기준 이름 하나가 곧바로 조회 두 건
 * (`/packages/similar` · `/packages`)이 되므로, 형식이 아닌 이름을 그대로 넘기면
 * 링크 하나가 매번 왕복 두 번을 버리고 V004 만 받아 온다. 상한도 같다 — 서버는 네 개를
 * 받으면 V002 로 **요청 전체**를 거절해서 화면이 통째로 빈다.
 *
 * <h2>버리되 밝힌다</h2>
 *
 * 뺀 이름을 `dropped` · `rejected` 로 돌려준다. 조용히 자르면 주소에는 다섯 개가 적혀
 * 있는데 화면에는 세 개만 뜨고 어느 것이 빠졌는지 알 방법이 없다 — S15P21A506-187 이
 * 보고서 화면에서 없앤 실패가 그것이라, 같은 실패를 분석 화면에 새로 만들지 않는다.
 *
 * <h2>기준이 없으면 후보도 버린다</h2>
 *
 * `?with=` 만 있는 주소는 비교의 기준이 없어 고른 것을 되살릴 자리가 없다. 이때는
 * `dropped` 에 담지 않고 조용히 버린다 — 화면이 빈 1단계로 열려 "아무것도 고르지 않은
 * 상태" 임이 그대로 보이기 때문이다. 세 개를 골랐다고 믿게 만드는 위의 실패와 다르다.
 */
export function readAnalyzeSelection(
  rawBase: string | null,
  rawWith: string | null,
): AnalyzeSelection {
  const rejected: string[] = []

  const baseInput = rawBase?.trim() ?? ''
  const base = baseInput ? normalize(baseInput) : null
  if (baseInput && !base) rejected.push(baseInput)

  if (!base) return { ...EMPTY, rejected }

  const picked: string[] = []
  const dropped: string[] = []
  // 기준도 이미 한 자리를 쓴다. 같은 이름이 후보로 또 들어오면 칩이 두 번 뜨고 셈이 어긋난다.
  const seen = new Set([base])

  for (const part of (rawWith ?? '').split(',')) {
    const input = part.trim()
    if (!input) continue
    const name = normalize(input)
    if (!name) {
      rejected.push(input)
      continue
    }
    if (seen.has(name)) continue
    seen.add(name)
    if (picked.length >= MAX_PICKED) {
      dropped.push(name)
      continue
    }
    picked.push(name)
  }

  return { base, picked, dropped, rejected }
}

/**
 * 위를 렌더 사이에 붙잡아 둔다.
 *
 * **네 값을 한 {@link useMemo} 안에서 만든다.** 밖에서 따로 잘라내면 렌더마다 새 배열이
 * 나오고, 그 배열이 그대로 effect 나 memo 의 의존성에 들어가면 서로를 깨우는 고리가 된다
 * (S15P21A506-187 이 보고서 화면에서 같은 이유로 한 memo 에 묶어 두었다).
 * 쿼리 키는 구조로 해시되므로 참조만으로 재조회가 나지는 않지만, 의존성 배열은 참조로 본다.
 */
export function useAnalyzeSelection(
  rawBase: string | null,
  rawWith: string | null,
): AnalyzeSelection {
  return useMemo(() => readAnalyzeSelection(rawBase, rawWith), [rawBase, rawWith])
}
