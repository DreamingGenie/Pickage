import { ShareDonut } from '@/components/charts/version-share'
import { SHARE_FILLS } from '@/components/charts/tokens'
import type {
  RemovalCounts,
  RemovalReasonsDataStatus,
} from '@/routes/report/ecosystem/removal-reasons-model'
import { cn } from '@/lib/utils'

/**
 * 이탈 사유 도넛 — 패키지 하나 (S15P21A506-410, 재설계 S15P21A506-427).
 *
 * **누적 막대가 아니라 도넛이다.** 막대였을 때는 막대 "안"의 두 색(대체 없이/함께 제거)이
 * 항상 100%를 채우는데도, 막대 "전체 길이"가 비교 패키지 중 최댓값 대비 상대 길이라
 * 짧게 그려진 패키지는 마치 셋째 범주가 빠진 것처럼 보였다(리뷰에서 확인된 오해).
 *
 * 도넛은 그 자체로 "안에서 100%" 를 형태로 보장해 그 오해가 생기지 않는다. 패키지 간
 * 규모 비교(막대 길이가 하던 역할)는 필요 없다 — 이 지표에서 중요한 것은 "이 패키지가 뺀
 * 이유의 구성" 이지 다른 패키지와의 상대 크기가 아니다.
 *
 * **도넛 가운데는 비율(%)이 아니라 총 이탈 건수다** — 비율은 이미 아래 범례에 있어 도넛
 * 가운데까지 %를 반복하면 중복이다(리뷰 지적). 대신 총 이탈 건수를 가운데 크게 두고,
 * 같은 값을 두 번(줄 하나 + 도넛 가운데) 적지 않도록 별도의 "이탈 전이" 줄은 두지 않는다.
 * 세로로 쌓아 도넛을 키우고(가로 공백이 아니라 세로 높이를 쓴다), 패키지 간 의존자 수
 * 비교처럼 단위가 다른 부가 정보("뺀 프로젝트 N개")는 화면을 덜 산만하게 하려고 뺐다.
 *
 * `data_status` 가 전체를 지배한다. **`NO_DATA` 를 `OUT_OF_SCOPE` 처럼 그리면 안 된다** —
 * 운영 대상의 58.5%가 `NO_DATA` 라 그걸 "분석 대상 아님" 으로 뭉개면 대부분의 패키지가
 * 잘못된 문구를 달게 된다. `NO_DATA` 는 **실제 값이 0** 이고, 좋은 소식이다.
 */
export function RemovalBars({
  counts,
  dataStatus,
  className,
}: {
  counts: RemovalCounts | null
  dataStatus: RemovalReasonsDataStatus
  className?: string
}) {
  /**
   * **`counts` 가 있어야 아는 것이다.** dataStatus 만 보면, 계약이 어긋나
   * (COMPLETE 인데 필드가 null) 어댑터가 counts 를 떨어뜨린 경우에도 `0` 을 확신에 차서
   * 그리게 된다 — "몰라서 못 셌다" 가 "세어 보니 없었다" 로 보인다. 이 패널이 가장
   * 경계하는 혼동이라(NO_DATA 와 구분하는 것이 완료 기준) 여기서 막는다.
   */
  const known = (dataStatus === 'COMPLETE' || dataStatus === 'NO_DATA') && counts !== null
  const total = counts?.removals ?? 0

  /**
   * **한쪽만 반올림하고 다른 쪽은 100 에서 뺀다.** 둘을 각자 Math.round 하면 합이
   * 101%(또는 99%)로 보인다 — removals=8 · no=3 · with=5 면 37.5→38, 62.5→63 이다.
   * `no + with = removals` 는 DB CHECK 로 보장되는 값이라 화면에서 깨지면 안 된다.
   */
  const noPct = total > 0 ? ((counts?.noReplacement ?? 0) / total) * 100 : 0
  const noPercent = total > 0 ? Math.round(noPct) : null
  const withPercent = noPercent === null ? null : 100 - noPercent

  if (known && counts && total > 0) {
    return (
      <div className={cn('flex flex-col items-center gap-3', className)}>
        <ShareDonut
          size={104}
          ariaLabel="이탈 사유 비율"
          groups={[
            { label: '대체 없이 제거', share: noPct / 100 },
            { label: '다른 것과 함께 제거', share: (100 - noPct) / 100 },
          ]}
          fills={[SHARE_FILLS[0], SHARE_FILLS[2]]}
          // 총 건수를 가운데에 둔다 — %는 아래 범례에 이미 있어 반복하지 않는다.
          centerText={{ primary: total.toLocaleString(), secondary: '총 이탈' }}
        />
        <dl className="flex w-full max-w-64 flex-col gap-1.5">
          {/* 대체 없이 제거가 이 지표의 결론이라 먼저·굵게 둔다. */}
          <Legend
            fill={SHARE_FILLS[0]}
            label="대체 없이 제거"
            value={counts.noReplacement}
            percent={noPercent}
            strong
          />
          <Legend
            fill={SHARE_FILLS[2]}
            label="다른 것과 함께 제거"
            value={counts.withReplacement}
            percent={withPercent}
          />
        </dl>
      </div>
    )
  }

  const message =
    dataStatus === 'NO_DATA'
      ? '이 기간에 뺀 프로젝트가 없습니다'
      : dataStatus === 'OUT_OF_SCOPE'
        ? '분석 대상 아님 · top-100k 밖'
        : dataStatus === 'NOT_COMPUTED'
          ? '준비 중'
          : // 계약상 COMPLETE·NO_DATA 면 값이 와야 한다. 안 왔으면 0 으로 메우지 않고 그 사실을 말한다.
            '값을 받지 못했습니다'

  return (
    <div className={cn('flex min-h-32 flex-col items-center justify-center', className)}>
      <p className="text-base text-muted-foreground">{message}</p>
    </div>
  )
}

function Legend({
  fill,
  label,
  value,
  percent,
  strong,
}: {
  fill: string
  label: string
  value: number
  /** 부르는 쪽이 한 번만 계산해 넘긴다 — 각자 반올림하면 둘의 합이 100 이 안 된다. */
  percent: number | null
  strong?: boolean
}) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="h-2.5 w-2.5 shrink-0 rounded-[3px]"
        style={{ background: fill }}
        aria-hidden
      />
      <dt className={cn('text-base', strong ? 'text-foreground' : 'text-muted-foreground')}>
        {label}
      </dt>
      <dd
        className={cn(
          'ml-auto font-mono text-base tabular-nums',
          strong ? 'font-medium text-foreground' : 'text-muted-foreground',
        )}
      >
        {value.toLocaleString()}
        {percent !== null && <span className="ml-1.5 text-muted-foreground">{percent}%</span>}
      </dd>
    </div>
  )
}
