import { describe, expect, it } from 'vitest'

import { mockMigrationPairs } from '@/api/mock/handlers'
import { MOCK_MIGRATION_PAIRS_DEV, MOCK_MIGRATION_PAIRS_REGULAR } from '@/api/mock/dataset'

/**
 * **mock 이 서버가 낼 수 없는 값을 내지 않는지** 본다 (S15P21A506-424).
 *
 * 깨지면 알게 되는 것 — 화면이 <b>실제로는 만나지 않을 상태</b>로 개발된다. 실제로 그
 * 일이 있었다: `a_pct` 를 `share_pm_pct * 3.6` 으로 지어냈더니 share 31% 인 행에서
 * <b>111.6%</b> 가 나와 말풍선에 그대로 떴다. 비율이 100을 넘을 수 없다는 것은 눈으로는
 * 당연한데, 픽스처를 손으로 적을 때는 그 당연한 것이 지켜지지 않는다.
 *
 * 서버 쪽 근거는 DB 제약이다 — `CK_MIGRATION_PAIR_PCT_RANGE` 가 네 비율을 0~100 으로
 * 묶는다. 실측 16,837쌍의 `a_pct` 최댓값도 정확히 100.0 이다.
 *
 * `handlers.ts` 머리말이 "응답 모양뿐 아니라 규칙도 흉내낸다" 고 적어 둔 그 규칙이 이것이다.
 */

const PCT_FIELDS = ['share_pm_pct', 'share_pct', 'a_pct'] as const

describe('mock 픽스처가 DB 제약을 지킨다', () => {
  it('모든 비율이 0~100 안에 있다', async () => {
    for (const kind of ['regular', 'dev'] as const) {
      const res = await mockMigrationPairs(['winston', 'pino', 'bunyan'], kind)
      for (const series of res.series) {
        for (const dest of series.destinations) {
          for (const field of PCT_FIELDS) {
            expect(
              dest[field],
              `${kind} ${series.name} → ${dest.name} ${field}`,
            ).toBeLessThanOrEqual(100)
            expect(
              dest[field],
              `${kind} ${series.name} → ${dest.name} ${field}`,
            ).toBeGreaterThanOrEqual(0)
          }
        }
        if (series.etc) {
          expect(series.etc.share_pm_pct).toBeLessThanOrEqual(100)
          expect(series.etc.share_pm_pct).toBeGreaterThanOrEqual(0)
        }
      }
    }
  })

  it('한 패키지의 점유율 합이 100 을 넘지 않는다', () => {
    // 상위 5 + 그 밖은 같은 분모를 나눠 가진다. 합이 100 을 넘으면 막대가 삐져나가고
    // "나머지" 가 음수가 된다 — 화면이 채우다 만 자리를 그리는 것이 요점이라 치명적이다.
    for (const table of [MOCK_MIGRATION_PAIRS_REGULAR, MOCK_MIGRATION_PAIRS_DEV]) {
      for (const [name, fixture] of Object.entries(table)) {
        const sum =
          (fixture.destinations ?? []).reduce((acc, d) => acc + d.sharePmPct, 0) +
          (fixture.etc?.sharePmPct ?? 0)
        expect(sum, `${name} 의 점유율 합`).toBeLessThanOrEqual(100)
      }
    }
  })

  it('a_pct 는 도착지 중 몫보다 크거나 같다', () => {
    // 분모가 다르다 — a_pct 는 이탈 전체, share_pm_pct 는 도착지들 사이의 몫이다.
    // 실측 16,837쌍 중 90.4% 에서 a_pct 가 더 크다. mock 이 반대로 적혀 있으면 두 수의
    // 뜻을 헷갈린 것이고, 화면 문장("지운 경우의 N%")이 거짓이 된다.
    for (const table of [MOCK_MIGRATION_PAIRS_REGULAR, MOCK_MIGRATION_PAIRS_DEV]) {
      for (const [name, fixture] of Object.entries(table)) {
        for (const d of fixture.destinations ?? []) {
          expect(d.aPct, `${name} → ${d.name}`).toBeGreaterThanOrEqual(d.sharePmPct)
        }
      }
    }
  })
})
