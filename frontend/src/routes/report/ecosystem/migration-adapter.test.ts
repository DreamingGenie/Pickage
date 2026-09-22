import { describe, expect, it } from 'vitest'

import type {
  MigrationDestinationWire,
  MigrationPairsResponse,
  MigrationSeriesItem,
} from '@/api/types'
import { toMigrationModel } from '@/routes/report/ecosystem/migration-adapter'
import { coveredPct, crossDirections } from '@/routes/report/ecosystem/migration-model'

/**
 * 이 지표가 화면에서 거짓말을 하게 되는 세 자리만 고정한다.
 *
 * 1. **점유율 합을 100 으로 보이게 만드는 것** — 분모가 표에 적재되지 않은 쌍까지 포함하므로
 *    합이 100 이 아닌 것이 정상이다. 실측에서 출발 패키지의 79.7%가 99.5% 에 못 미치고
 *    중앙값이 25.7% 라, 여기가 무너지면 대부분의 패키지에서 도착지가 네 배 부풀려진다.
 * 2. **모르는 등급을 올려 읽는 것** — 없는 확신을 사용자에게 준다.
 * 3. **비교 패키지 사이의 방향을 합치거나 빠뜨리는 것** — 기획의 "최대 6개 방향" 이다.
 */

const dest = (
  name: string,
  sharePmPct: number,
  extra: Partial<MigrationDestinationWire> = {},
): MigrationDestinationWire => ({
  name,
  votes: 20,
  co_events: 32,
  publisher_months: 14,
  dependents: 24,
  lift: 800,
  share_pm_pct: sharePmPct,
  share_pct: sharePmPct + 2,
  evidence: 'recommended',
  variant: false,
  first_seen: '2019-03-11',
  last_seen: '2026-07-28',
  ...extra,
})

const series = (
  name: string,
  destinations: MigrationDestinationWire[],
  extra: Partial<MigrationSeriesItem> = {},
): MigrationSeriesItem => ({
  name,
  snapshot_at: '2026-08-31',
  share_basis: 'publisher_months',
  destinations,
  etc: null,
  observed_pairs: destinations.length,
  data_status: 'COMPLETE',
  ...extra,
})

const responseOf = (items: MigrationSeriesItem[]): MigrationPairsResponse => ({
  metric: 'migration_pairs',
  kind: 'regular',
  series: items,
  not_found: [],
})

describe('점유율 — 100 으로 채우지 않는다', () => {
  it('상위와 그 밖을 더한 값이 그대로 나온다 (100 이 아니다)', () => {
    const model = toMigrationModel(
      responseOf([
        series('winston', [dest('pino', 21.4), dest('bunyan', 14.8)], {
          etc: { pairs: 2, share_pm_pct: 8.3, below_filter: 2 },
        }),
      ]),
      ['winston'],
    )

    // 21.4 + 14.8 + 8.3 = 44.5. 나머지 55.5%가 "근거가 약해 뺀 이동" 이고, 그 자리가
    // 화면에서 가장 중요한 정보다. 여기서 100 으로 맞추면 막대가 꽉 차 보인다.
    expect(coveredPct(model.packages[0]!)).toBeCloseTo(44.5, 5)
  })

  it('반올림으로 100 을 넘어도 위로 자른다', () => {
    // 실측에서 합이 100.2 인 출발 패키지가 있다(소수 한 자리 반올림 때문). 자르지 않으면
    // 남는 자리가 음수가 되어 빗금 띠의 폭이 뒤집힌다.
    const model = toMigrationModel(
      responseOf([series('lodash', [dest('lodash-es', 60.1), dest('ramda', 40.1)])]),
      ['lodash'],
    )

    expect(coveredPct(model.packages[0]!)).toBe(100)
  })
})

describe('근거 강도 — 모르면 낮춘다', () => {
  it('처음 보는 등급은 loose 로 떨어진다', () => {
    // 서버가 등급을 늘리면 화면이 모르는 문자열을 받는다. strict 로 올리면 근거가 약한
    // 이동에 "근거 강함" 이 붙어 없는 확신을 준다 — 배지가 낮게 보이는 쪽이 안전하다.
    const model = toMigrationModel(
      responseOf([series('winston', [dest('pino', 10, { evidence: 'exceptional' })])]),
      ['winston'],
    )

    expect(model.packages[0]!.destinations[0]!.evidence).toBe('loose')
  })
})

describe('비교 패키지 사이의 방향', () => {
  it('양쪽이 다 관측되면 둘 다 남긴다', () => {
    // 합치거나 순이동을 내면 안 된다 — 분모가 서로 다른 두 수이고, 양방향 자체가
    // "같은 물건의 두 포장" 이라는 신호다.
    const model = toMigrationModel(
      responseOf([
        series('winston', [dest('pino', 21.4)]),
        series('pino', [dest('winston', 31.0)]),
      ]),
      ['winston', 'pino'],
    )

    expect(crossDirections(model)).toEqual([
      { from: 'winston', to: 'pino', sharePmPct: 21.4, evidence: 'recommended', variant: false },
      { from: 'pino', to: 'winston', sharePmPct: 31.0, evidence: 'recommended', variant: false },
    ])
  })

  it('비교 중이 아닌 도착지는 빠진다', () => {
    // consola 는 winston 의 도착지이지만 지금 비교 중이 아니다. 이 줄에 끼면 사용자는
    // 고르지도 않은 패키지를 비교 대상으로 읽는다.
    const model = toMigrationModel(
      responseOf([
        series('winston', [dest('pino', 21.4), dest('consola', 9.1)]),
        series('pino', []),
      ]),
      ['winston', 'pino'],
    )

    expect(crossDirections(model).map((d) => d.to)).toEqual(['pino'])
  })
})

describe('세어 보지 않은 것을 0 으로 만들지 않는다', () => {
  it('observedPairs 가 null 이면 null 그대로 둔다', () => {
    // OUT_OF_SCOPE·NOT_COMPUTED 는 "세어 보니 없었다"(0)가 아니라 "세지 않았다" 다.
    const model = toMigrationModel(
      responseOf([
        series('morgan', [], {
          snapshot_at: null,
          observed_pairs: null,
          data_status: 'OUT_OF_SCOPE',
        }),
      ]),
      ['morgan'],
    )

    expect(model.packages[0]!.observedPairs).toBeNull()
    expect(model.packages[0]!.snapshotAt).toBeNull()
  })
})

describe('순서는 서버가 아니라 비교 순서를 따른다', () => {
  it('요청한 이름 순서로 재배열한다', () => {
    // 칩 줄·다른 패널이 이 순서로 색을 정한다. 어긋나면 같은 패키지가 패널마다 다른 색이 된다.
    const model = toMigrationModel(responseOf([series('pino', []), series('winston', [])]), [
      'winston',
      'pino',
    ])

    expect(model.packages.map((p) => p.key)).toEqual(['winston', 'pino'])
  })
})
