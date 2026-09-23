import type { DependencyKindParam } from '@/api/types'
import { josa } from '@/lib/josa'

/**
 * 관측된 교체 흐름 view-model (S15P21A506-424).
 *
 * `removal-reasons-model.ts` 와 같은 패턴(wire-근접, 얇은 변환)이되 **축이 다르다** —
 * 저쪽은 구간(1y·3y·5y)을 고르고 이쪽은 **의존 종류**(실행용·개발용)를 고른다. 연속한
 * 릴리스를 전부 훑은 결과라 "몇 년치" 라는 개념이 성립하지 않기 때문이다.
 *
 * 그래서 `transitions-model` 의 프리셋을 가져오지 않는다. 같은 화면에 있어도 두 선택기가
 * 고르는 것이 다르므로, 값을 공유하면 한쪽을 바꿀 때 다른 쪽이 딸려 간다.
 */

export const DEPENDENCY_KINDS: { key: DependencyKindParam; label: string; hint: string }[] = [
  { key: 'regular', label: '실행용', hint: 'npm 전체에서 관측' },
  { key: 'dev', label: '개발용', hint: '다운로드 상위 10만에서 관측' },
]

export const DEFAULT_KIND: DependencyKindParam = 'regular'

export type MigrationDataStatus =
  'COMPLETE' | 'INSUFFICIENT_EVIDENCE' | 'NO_DATA' | 'OUT_OF_SCOPE' | 'NOT_COMPUTED'

/** 근거 강도. 행을 지우는 대신 붙이는 배지다(S15P21A506-211 결정 1). */
export type MigrationEvidence = 'strict' | 'recommended' | 'loose'

export interface MigrationDestination {
  name: string
  /**
   * 점유율. 분모는 표가 아니라 서로 다른 (발행자 × 달) 의 수다.
   *
   * **한 패키지 안의 값을 다 더해도 100 이 아니다.** 분모가 빌더의 `lift>=5` 쌍 전체인데
   * 표에는 근거가 약한 것을 뺀 나머지만 적재되기 때문이다. 화면이 100 으로 정규화하면
   * 모든 도착지가 네 배 가까이 부풀려진다 — 그래서 남는 자리를 그대로 남긴다.
   */
  sharePmPct: number
  /** 가중 표. 정수가 아니다. */
  votes: number
  /** 서로 다른 (발행자 × 달) 의 수. 한 조직의 일괄 변경을 걸러 내는 값이다. */
  publisherMonths: number
  /**
   * 이 바꿈을 <b>실제로 한 프로젝트 수</b>(중복 접음).
   *
   * 화면이 "얼마나 믿을 만한가" 를 말할 때 쓰는 수다. `votes` 는 가중 합이라 사람에게
   * 뜻이 전해지지 않고, `publisherMonths` 는 사람 수가 아니라 (만든 사람 × 달) 조합이라
   * "N명" 으로 옮겨 적으면 <b>거짓말이 된다</b> — 한 사람이 열 달에 걸쳐 하면 10이다.
   * 이 열만이 "프로젝트 몇 곳" 으로 그대로 읽힌다.
   */
  dependents: number
  /**
   * 그 패키지를 지운 경우 중 이것을 함께 넣은 비율.
   *
   * `sharePmPct`(도착지들 사이의 몫)와 다르다. 이쪽은 <b>분모가 이탈 전체</b>라
   * "지운 사람 다섯 중 하나가 이걸 골랐다" 처럼 읽힌다.
   */
  aPct: number
  evidence: MigrationEvidence
  /**
   * 양방향으로 관측됐다 — **같은 물건의 두 포장**일 수 있다(lodash ↔ lodash-es).
   * 지우지 않고 표시만 다르게 한다(결정 4 ③).
   */
  variant: boolean
  firstSeen: string
  lastSeen: string
}

/** 상위 밖을 접은 칸. 이름을 세우지 않는 이유는 꼬리의 82%가 일회성 추가라서다. */
export interface MigrationEtc {
  pairs: number
  sharePmPct: number
  /** 그중 기본 필터에 못 미친 수. "근거가 약해 접었다" 를 말할 근거. */
  belowFilter: number
}

export interface PackageMigration {
  key: string
  /** 이 종류의 기준일. 종류마다 다르다. 읽을 행이 없으면 null. */
  snapshotAt: string | null
  /** 서버가 값으로 실어 보낸다(`"publisher_months"`). 캡션에 그대로 쓴다. */
  shareBasis: string
  dataStatus: MigrationDataStatus
  /** 기본 필터를 통과한 상위 5개. `INSUFFICIENT_EVIDENCE` 면 비어 있다. */
  destinations: MigrationDestination[]
  etc: MigrationEtc | null
  /** 필터 전 관측된 쌍의 수. 세어 보지 않았으면 null — 0 으로 바꾸지 않는다. */
  observedPairs: number | null
}

export interface MigrationModel {
  kind: DependencyKindParam
  packages: PackageMigration[]
  notFound: string[]
}

export const EMPTY_MIGRATION_MODEL: MigrationModel = {
  kind: DEFAULT_KIND,
  packages: [],
  notFound: [],
}

/**
 * 상위와 `etc` 를 더한 몫. **나머지(100 − 이 값)가 "집계에서 뺀 이동" 이다.**
 *
 * 화면이 이 값을 쓰는 이유는 남는 자리를 <b>보여 주기</b> 위해서다. 정규화의 반대다 —
 * 실측에서 출발 패키지의 79.7%가 99.5% 에 못 미치고 중앙값이 25.7% 이므로, 남는 자리를
 * 감추면 대부분의 패키지에서 화면이 실제와 다른 이야기를 한다.
 *
 * 반올림 때문에 100 을 살짝 넘는 패키지가 있어(실측 최대 100.2) 위로 자른다.
 */
export function coveredPct(pkg: PackageMigration): number {
  const sum =
    pkg.destinations.reduce((acc, d) => acc + d.sharePmPct, 0) + (pkg.etc?.sharePmPct ?? 0)
  return Math.min(100, sum)
}

export const EVIDENCE_LABEL: Record<MigrationEvidence, string> = {
  strict: '근거 강함',
  recommended: '근거 보통',
  loose: '근거 약함',
}

/**
 * 배지에 마우스를 올렸을 때 뜨는 <b>한 문장</b> — 그 행에서 <b>실제로 관측된 수</b>다.
 *
 * <b>문턱값을 말풍선에 싣지 않는다.</b> 처음에는 "(만든 사람 × 달) 10곳 이상 · 바뀐 횟수
 * 12회 이상 …" 을 그대로 띄웠는데, 그건 <b>코드를 짜면서 확인하는 값</b>이지 화면 앞의
 * 사람이 알아야 할 것이 아니다. 다음에는 "여러 곳에서 오랜 기간에 걸쳐…" 로 바꿔 봤는데
 * 이번에는 <b>추상적이어서</b> 아무 수도 전하지 못했다.
 *
 * 셋째 판이 이것이다 — <b>그 쌍의 실제 수를 그대로 말한다.</b> 등급 낱말을 따로 변호할
 * 필요가 없어진다. 8.4%(50곳)를 보면 "근거 강함" 이 스스로 납득되고, 3.8%(41곳)면 배지와
 * 어긋나는 것이 눈에 보인다.
 *
 * <b>비율이 앞에 오고 실수가 괄호로 간다</b>(S15P21A506-468). 사람이 먼저 알고 싶은 것은
 * "몇 곳" 이 아니라 "얼마나" 다 — 397곳이 많은 수인지는 모집단을 알아야 판단할 수 있지만
 * 20.8% 는 그 자체로 읽힌다.
 *
 * <b>이름을 문장에 넣는다.</b> 예전에는 조사(을/를)가 갈리는 것이 부담스러워 "이 패키지" 로
 * 가리켰는데, 같은 줄에 이름이 있어도 <b>문장만 따로 읽으면 무엇 이야기인지 알 수 없다.</b>
 * 조사는 {@link josa} 가 붙이고, 그 근사가 어긋나도 뜻은 달라지지 않는다.
 *
 * <b>값이 없을 수 있다고 보고 만든다.</b> 타입은 `number` 지만 그것은 컴파일 때의 약속일
 * 뿐이고, 런타임에 오는 것은 서버가 준 JSON 이다. `undefined.toFixed()` 가 render 중에
 * 터지면 이 패널만 비는 것이 아니라 라우터의 에러 경계가 받아 <b>보고서 페이지 전체가 빈
 * 화면이 된다</b> — 이 화면에서 실제로 한 번 겪은 고장 방식이다.
 */
export function observationHint(
  from: string,
  dest: { name: string; dependents: number | null | undefined; aPct: number | null | undefined },
): string {
  const share = typeof dest.aPct === 'number' ? `${dest.aPct.toFixed(1)}%` : null
  const projects = typeof dest.dependents === 'number' ? dest.dependents.toLocaleString() : null

  if (share === null) return '관측된 수를 받지 못했어요'

  const removed = `${from}${josa(from, '을', '를')}`
  const added = `${dest.name}${josa(dest.name, '을', '를')}`
  const count = projects === null ? '' : `(${projects}곳)`
  return `${removed} 지운 프로젝트 중 ${share}${count}가 ${added} 넣었어요`
}

/**
 * 같은 배지의 <b>판정 문턱</b>. 모달의 풀이표에서만 쓴다.
 *
 * 남겨 두는 이유는 등급이 상대 순위가 아니라 <b>고정된 문턱</b>이기 때문이다 — 같은
 * 화면에 강함이 없다고 해서 1위가 강함이 되지 않는다.
 *
 * <b>단위를 문구 안에 넣는다.</b> 예전에는 "널리 10 · 자주 12번" 처럼 줄이고 표 위에서
 * 그 두 낱말을 정의했는데, <b>용어집을 먼저 읽어야 이해되는 설명은 설명이 아니다.</b>
 * 반복이 생기더라도 한 줄이 혼자 읽히는 쪽이 낫다.
 */
export const EVIDENCE_RULE: Record<MigrationEvidence, string> = {
  strict:
    '변경이 보인 횟수 12회 이상 · 서로 다른 (만든 사람 × 달) 10가지 이상 · 그 패키지를 지운 경우의 3% 이상',
  recommended:
    '변경이 보인 횟수 8회 이상 · 서로 다른 (만든 사람 × 달) 5가지 이상 · 도착지 중 몫 10% 이상',
  loose: '위 두 줄에 못 미쳐요',
}

/**
 * 배지 이름. <b>"변종" 이 아니라 "양방향" 이다</b> (S15P21A506-424 4층 검증, 2026-09-22).
 *
 * `-211` 결정 4 ③ 은 이 플래그를 "같은 물건의 두 포장(lodash ↔ lodash-es)" 으로 보고
 * "변종" 이라 부르라고 적었다. <b>실측이 그 전제를 뒤집었다</b> — 상위 5에 서는 자리
 * 4,182개 중 1,598개(38.2%)가 이 플래그를 단다. `rxjs → tslib`, `moment → lodash` 도
 * 참이다. 널리 쓰이는 패키지 둘은 어디에선가 서로 반대로도 바뀌기 때문이다.
 */
export const VARIANT_LABEL = '양방향'

export const VARIANT_HINT = '반대 방향 이동도 관측됐어요'

/** 모달에서만 쓰는 부연. 말풍선에 넣기에는 길고, 판단을 사람에게 남기는 문장이다. */
export const VARIANT_RULE =
  '같은 것의 다른 포장(lodash ↔ lodash-es)일 수도, 서로 오간 것일 수도 있어요'

/**
 * 비교 중인 패키지끼리의 이동만 골라낸다 — **최대 6개 방향**(S15P21A506-136 기획).
 *
 * 3개를 비교하면 자기 자신을 뺀 방향이 3×2 = 6 개다. 이 목록이 따로 필요한 이유는,
 * 패키지별 막대는 "이 패키지를 떠난 사람들이 어디로 갔나" 만 보여 주기 때문이다 —
 * 그중 <b>어느 것이 지금 비교 중인 다른 패키지인지</b>는 이름을 하나씩 대조해야 알 수 있다.
 * 사용자가 실제로 궁금해하는 것("이 둘 사이에 이동이 있었나")이 그 대조에 묻힌다.
 *
 * <b>양쪽 방향이 다 있으면 둘 다 남긴다.</b> 합치거나 순이동을 계산하지 않는다 — 분모가
 * 서로 다른 두 수라 빼면 뜻이 없고, 양방향 자체가 "같은 물건의 두 포장" 이라는 신호다.
 */
export interface MigrationDirection {
  from: string
  to: string
  sharePmPct: number
  evidence: MigrationEvidence
  variant: boolean
  /** 배지 말풍선이 쓰는 두 수. 아래 막대와 **같은 문장**을 내기 위해 함께 나른다. */
  dependents: number
  aPct: number
}

export function crossDirections(model: MigrationModel): MigrationDirection[] {
  const compared = new Set(model.packages.map((p) => p.key))
  const out: MigrationDirection[] = []
  for (const pkg of model.packages) {
    for (const dest of pkg.destinations) {
      if (dest.name === pkg.key || !compared.has(dest.name)) continue
      out.push({
        from: pkg.key,
        to: dest.name,
        sharePmPct: dest.sharePmPct,
        evidence: dest.evidence,
        variant: dest.variant,
        dependents: dest.dependents,
        aPct: dest.aPct,
      })
    }
  }
  return out
}
