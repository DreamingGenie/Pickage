import { HatchDef } from '@/components/charts/version-share'
import { SHARE_FILLS } from '@/components/charts/tokens'
import type {
  RemovalCounts,
  RemovalReasonsDataStatus,
} from '@/routes/report/ecosystem/removal-reasons-model'
import { cn } from '@/lib/utils'

/**
 * 이탈 사유 막대 — 패키지 하나.
 *
 * `TransitionBars` 와 달리 **범주가 둘이고 서로 합쳐 전체가 된다**
 * (`no_replacement + with_replacement = removals`, 서버 DB CHECK). 그래서 네 개를
 * 나란히 세우지 않고 **누적 막대 하나**로 그린다 — 비율이 이 지표의 결론이기 때문이다.
 *
 * `data_status` 가 행 전체를 지배한다. **`NO_DATA` 를 `OUT_OF_SCOPE` 처럼 그리면 안 된다** —
 * 운영 대상의 58.5%가 `NO_DATA` 라 그걸 "분석 대상 아님" 으로 뭉개면 대부분의 패키지가
 * 잘못된 문구를 달게 된다. `NO_DATA` 는 **실제 값이 0** 이고, 좋은 소식이다.
 */
export function RemovalBars({
  counts,
  dataStatus,
  max,
  className,
}: {
  counts: RemovalCounts | null
  dataStatus: RemovalReasonsDataStatus
  /** 비교 패키지 전체를 통틀어 호출자가 한 번 계산한 값 — 막대 길이를 패키지끼리 비교하려면 공유해야 한다. */
  max: number
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
  // 막대 전체가 차지하는 폭. 0 이면 빈 트랙만 남아 "없음" 이 형태로 보인다.
  const trackPct = known && max > 0 && total > 0 ? Math.max((total / max) * 100, 2) : 0
  const noPct = total > 0 ? ((counts?.noReplacement ?? 0) / total) * 100 : 0
  /**
   * **한쪽만 반올림하고 다른 쪽은 100 에서 뺀다.** 둘을 각자 Math.round 하면 합이
   * 101%(또는 99%)로 보인다 — removals=8 · no=3 · with=5 면 37.5→38, 62.5→63 이다.
   * `no + with = removals` 는 DB CHECK 로 보장되는 값이라 화면에서 깨지면 안 된다.
   */
  const noPercent = total > 0 ? Math.round(noPct) : null
  const withPercent = noPercent === null ? null : 100 - noPercent

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <svg width="0" height="0" aria-hidden className="absolute">
        <HatchDef />
      </svg>

      <div className="flex items-baseline justify-between gap-2">
        <span className="text-base text-muted-foreground">이탈 전이</span>
        <span className="font-mono text-base tabular-nums">
          {known ? total.toLocaleString() : '—'}
        </span>
      </div>

      <span
        className={cn(
          'flex h-3 overflow-hidden rounded-sm',
          dataStatus === 'NOT_COMPUTED' ? 'border border-dashed bg-transparent' : 'bg-muted',
        )}
      >
        {dataStatus === 'OUT_OF_SCOPE' ? (
          <svg width="100%" height="100%" viewBox="0 0 100 10" preserveAspectRatio="none">
            {/* CSS 배경으로 SVG 패턴을 참조하면 Chrome 에서 안 그려진다 — `fill` 속성으로 직접 참조한다(ShareBars 와 같은 이유). */}
            <rect width="40" height="10" rx="2" fill="url(#pk-hatch)" />
          </svg>
        ) : trackPct > 0 ? (
          <span className="flex h-full" style={{ width: `${trackPct}%` }}>
            <span
              className="h-full"
              style={{ width: `${noPct}%`, background: SHARE_FILLS[0] }}
              aria-hidden
            />
            <span
              className="h-full"
              style={{ width: `${100 - noPct}%`, background: SHARE_FILLS[2] }}
              aria-hidden
            />
          </span>
        ) : null}
      </span>

      {known && counts ? (
        <dl className="flex flex-col gap-1">
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
      <span className="h-2.5 w-2.5 shrink-0 rounded-[3px]" style={{ background: fill }} aria-hidden />
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
