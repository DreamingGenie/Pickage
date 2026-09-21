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
 * 규모 비교(막대 길이가 하던 역할)는 위에 그대로 찍히는 "이탈 전이" 숫자가 대신한다 —
 * 굳이 도넛 크기까지 비교 용도로 쓸 필요가 없다(`Version Share` 도넛도 같은 원칙).
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

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-base text-muted-foreground">이탈 전이</span>
        <span className="font-mono text-base tabular-nums">
          {known ? total.toLocaleString() : '—'}
        </span>
      </div>

      {known && counts && total > 0 ? (
        <div className="flex items-center gap-4">
          <ShareDonut
            size={72}
            ariaLabel="이탈 사유 비율"
            groups={[
              { label: '대체 없이 제거', share: noPct / 100 },
              { label: '다른 것과 함께 제거', share: (100 - noPct) / 100 },
            ]}
            fills={[SHARE_FILLS[0], SHARE_FILLS[2]]}
            // 어느 쪽이 크든 "대체 없이 제거"가 이 지표의 결론이라 항상 가운데 둔다
            // (도넛 기본 동작인 "가장 큰 몫"에 맡기지 않는다).
            centerOverride={{ label: '대체 없이 제거', share: noPct / 100 }}
          />
          <dl className="flex min-w-0 flex-1 flex-col gap-1">
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
      ) : null}

      {dataStatus === 'NO_DATA' && (
        <p className="text-base text-muted-foreground">이 기간에 뺀 프로젝트가 없습니다</p>
      )}
      {dataStatus === 'OUT_OF_SCOPE' && (
        <p className="text-base text-muted-foreground">분석 대상 아님 · top-100k 밖</p>
      )}
      {dataStatus === 'NOT_COMPUTED' && <p className="text-base text-muted-foreground">준비 중</p>}
      {/* 계약상 COMPLETE·NO_DATA 면 네 숫자가 다 와야 한다. 안 왔으면 0 으로 메우지 않고 그 사실을 말한다. */}
      {(dataStatus === 'COMPLETE' || dataStatus === 'NO_DATA') && !counts && (
        <p className="text-base text-muted-foreground">값을 받지 못했습니다</p>
      )}

      {/*
        `dependents` 와 `removals` 는 **단위가 다르다**(의존자 수 vs 전이 건수). 나누지 않는다 —
        둘을 함께 보여주는 것은 "몇 번 일어났나" 와 "몇 명이 했나" 가 다르다는 것을 보이기 위해서다.
      */}
      {dataStatus === 'COMPLETE' && counts && (
        <p className="-mt-0.5 text-base text-muted-foreground/80">
          뺀 프로젝트 {counts.dependents.toLocaleString()}개가 일으킨 일입니다
        </p>
      )}
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
