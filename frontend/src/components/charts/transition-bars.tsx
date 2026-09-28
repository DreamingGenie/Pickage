import { Fragment } from 'react'

import { HatchDef, ShareDonut } from '@/components/charts/version-share'
import { SHARE_FILLS } from '@/components/charts/tokens'
import {
  activityShares,
  freshnessSegments,
  type TransitionCounts,
  type TransitionDataStatus,
} from '@/routes/report/ecosystem/transitions-model'
import { cn } from '@/lib/utils'

/** 값(전체 대비 막대) · 비율(활동 대비 도넛) — 패널 전체가 공유하는 "값/비율" 토글이 고른다. */
export type TransitionBarsMode = 'value' | 'ratio'

type CategoryKey = 'retained' | 'inflowAdopted' | 'outflow' | 'unobserved'

/** 고정 네 범주. 항상 이 순서로, 항상 넷 다 그린다 — `unobserved`를 빼거나 `retained`에
 *  합치면 유지율이 실제보다 높게 보이는 거짓 그래프가 된다(1년 구간 기준 최대 75%p 차이).
 *
 *  `unobserved`를 **"미관측"·"알 수 없음"으로 부르지 않는다**(S15P21A506-427) — 자료를 못 구한
 *  것처럼 읽히는데, 실제로는 기간의 양 끝에 선언이 남아 있다는 것을 알고 있다. 모르는 것은 그 사이에
 *  계속 쓸지 다시 검토했는가 뿐이고, 판단할 수 없는 이유는 **의존자가 이 기간에 릴리스를 내지 않아서**다.
 *  라벨 자리가 좁아 사실만 짧게 적고, 뜻은 패널의 계산 기준 모달이 맡는다. */
const CATEGORIES: { key: CategoryKey; label: string; fill: string }[] = [
  { key: 'retained', label: '유지', fill: SHARE_FILLS[0] },
  { key: 'inflowAdopted', label: '유입', fill: SHARE_FILLS[1] },
  { key: 'outflow', label: '이탈', fill: SHARE_FILLS[2] },
  { key: 'unobserved', label: '릴리스 없음', fill: SHARE_FILLS[3] },
]

const PLACEHOLDER_WIDTH = 40

/** 값이 0 이 아닌데 막대가 안 보이는 것을 막는 바닥값(%). 하위 줄에는 쓰지 않는다. */
const MIN_BAR_WIDTH = 2

/**
 * 유지·유입·이탈 네 범주 막대 — 패키지 하나 × kind 하나.
 *
 * `data_status`가 행 전체를 지배한다(백엔드 계약) — 카테고리별로 다른 상태를 섞지 않는다.
 * `OUT_OF_SCOPE`·`NOT_COMPUTED`를 0짜리 막대로 그리면 "아무도 안 쓴다"는 거짓말이 되므로,
 * 절대 `width: 0`이나 진짜 값처럼 보이는 자리로 그리지 않는다 — 둘 다 고정 placeholder
 * 폭에 서로 다른 질감(빗금 vs 점선 빈틀)을 써서 "값이 없다"는 것 자체가 형태로 보이게 한다.
 */
export function TransitionBars({
  counts,
  dataStatus,
  max,
  mode = 'ratio',
  className,
}: {
  counts: TransitionCounts | null
  dataStatus: TransitionDataStatus
  /** 비교 중인 패키지 전체를 통틀어 호출자가 한 번 계산한 값 — 여기서 스케일을
   *  독립적으로 잡으면 패키지끼리 막대 길이를 비교할 수 없게 된다. `ratio` 모드에서는
   *  쓰지 않는다(도넛은 패키지마다 자기 안에서 100%다). */
  max: number
  /**
   * **기본이 `ratio` 다** (S15P21A506-468). 값/비율 토글을 없애면서 화면에서 `value` 로
   * 부르는 곳이 사라졌다 — 막대와 `릴리스 없음` 분해(S15P21A506-431)는 코드로만 남아
   * 있고 시험이 지킨다. 되돌리려면 이 한 줄과 패널의 토글을 함께 살리면 된다.
   */
  mode?: TransitionBarsMode
  className?: string
}) {
  if (mode === 'ratio') {
    return <RatioDonut counts={counts} dataStatus={dataStatus} className={className} />
  }

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <svg width="0" height="0" aria-hidden className="absolute">
        <HatchDef />
      </svg>
      {CATEGORIES.map((cat) => (
        <Fragment key={cat.key}>
          <BarRow
            label={cat.label}
            fill={cat.fill}
            value={counts ? counts[cat.key] : null}
            dataStatus={dataStatus}
            max={max}
          />
          {cat.key === 'unobserved' &&
            freshnessSegments(counts?.unobservedFreshness ?? null).map((seg) => (
              <BarRow
                key={seg.key}
                label={seg.label}
                fill={cat.fill}
                value={seg.value}
                dataStatus={dataStatus}
                max={max}
                sub
              />
            ))}
        </Fragment>
      ))}
      {dataStatus === 'NO_DATA' && <p className="text-base text-muted-foreground">의존자 없음</p>}
      {dataStatus === 'OUT_OF_SCOPE' && (
        <p className="text-base text-muted-foreground">분석 대상 아님 · top-100k 밖</p>
      )}
      {dataStatus === 'NOT_COMPUTED' && <p className="text-base text-muted-foreground">준비 중</p>}
      {dataStatus === 'COMPLETE' && counts && counts.inflowRaw !== counts.inflowAdopted && (
        <p className="-mt-0.5 text-base text-muted-foreground/80">
          원시 유입 {counts.inflowRaw.toLocaleString()} · 신규 {counts.inflowNew.toLocaleString()}건
          포함
        </p>
      )}
    </div>
  )
}

/**
 * 활동 대비 비율 — 도넛 (S15P21A506-427, 재설계 S15P21A506-427 후속).
 *
 * 막대(값 모드)는 **전체 대비**다 — 1년 구간이면 `릴리스 없음` 하나가 화면을 먹어 나머지 셋을
 * 서로 비교할 수 없다. 그래서 판정한 의존자만 분모로 삼은 비율을 **도넛**으로 따로 보여준다.
 * 글로 "유지 72.6% · 유입 10.4% · 이탈 17.0%" 를 늘어놓는 것보다, 세 조각이 원 하나를 나눠
 * 가진 그림이 "본 것 중 무엇이 일어났나" 를 한눈에 전한다(리뷰에서 텍스트 줄이 안 읽힌다는
 * 지적을 받았다).
 *
 * 전체 대비(막대)와 활동 대비(도넛)를 **패널 전체가 공유하는 토글로 가른다** — 막대는 "얼마나 봤나",
 * 도넛은 "본 것 중 무엇이 일어났나" 이고, 한 화면에 억지로 같이 두면 서로 다른 분모의 숫자가
 * 뒤섞여 더 헷갈린다. 세로로 쌓아 도넛을 키운다 — 도넛 옆에 범례를 붙이면 칼럼 폭만 넓고
 * 안은 빈 카드가 된다(리뷰 지적).
 *
 * 분모가 `inflowAdopted`인 이유는 `activityShares` 주석에 있다.
 */
function RatioDonut({
  counts,
  dataStatus,
  className,
}: {
  counts: TransitionCounts | null
  dataStatus: TransitionDataStatus
  className?: string
}) {
  const shares = counts ? activityShares(counts) : null

  if (!shares) {
    const message =
      dataStatus === 'OUT_OF_SCOPE'
        ? '분석 대상 아님 · top-100k 밖'
        : dataStatus === 'NOT_COMPUTED'
          ? '준비 중'
          : '판정한 의존자가 없습니다'
    /**
     * **비율을 못 내도 수는 남긴다** (S15P21A506-468 리뷰).
     *
     * `activityShares` 는 판정한 의존자가 0 이면 null 이다 — 나눌 분모가 없으니 옳다.
     * 문제는 그때 `counts` 까지 버리고 문구 한 줄만 그렸다는 것이다. 값/비율 토글이
     * 있던 동안에는 값 모드로 바꾸면 릴리스 없음 막대에 실제 수가 보여 가려지지 않았는데,
     * 토글을 없애면서 <b>이 화면이 유일한 표시가 됐다.</b>
     *
     * 그대로 두면 의존자 412곳이 전부 이 기간에 릴리스를 안 낸 패키지가 "판정한 의존자가
     * 없습니다" 한 줄로 끝나 <b>의존자가 아예 없는 것처럼 읽힌다</b> — 이 패널이 가장
     * 경계하는 혼동("세어 보니 없었다" vs "몰라서 못 셌다")이다. 드문 경우도 아니다:
     * 로컬 실측에서 1년 구간 행의 11.9%(34,777/293,235), 3년 7.1%, 5년 4.4% 가 여기 걸린다.
     */
    const observed = counts ? counts.retained + counts.inflowAdopted + counts.outflow : 0
    const unobserved = counts?.unobserved ?? 0
    const population = observed + unobserved

    return (
      <div className={cn('flex min-h-32 flex-col items-center justify-center gap-2', className)}>
        <p className="text-base text-muted-foreground">{message}</p>
        {/* 셀 곳이 있었을 때만. `NO_DATA`(전부 0)에 "의존자 0 중" 을 붙이면 군더더기다. */}
        {population > 0 && (
          <p className="text-center text-base text-muted-foreground/80">
            의존자 {population.toLocaleString()} 중
            <br />
            <span className="text-muted-foreground/70">
              {unobserved.toLocaleString()} {CATEGORIES[3].label}
            </span>
          </p>
        )}
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col items-center gap-3', className)}>
      {/*
        캡션을 도넛 아래가 아니라 옆에 둔다 — 아래에 두면 두 줄로 접혀 "값" 모드보다 카드가
        눈에 띄게 길어졌다(리뷰 지적). 도넛을 살짝 왼쪽으로 밀어 생긴 옆자리를 쓴다.
      */}
      <div className="flex items-center gap-4">
        <ShareDonut
          size={104}
          ariaLabel="유지·유입·이탈 활동 대비 비율"
          groups={[
            { label: CATEGORIES[0].label, share: shares.retainedPct / 100 },
            { label: CATEGORIES[1].label, share: shares.inflowAdoptedPct / 100 },
            { label: CATEGORIES[2].label, share: shares.outflowPct / 100 },
          ]}
        />
        {/*
          **분모를 여기서만 말한다** (S15P21A506-468). 값(전체 대비) 모드가 사라지면서
          `릴리스 없음` 칸이 화면에서 없어졌는데, 그 줄이 없으면 도넛이 전체를 나눈 것처럼
          읽힌다 — 1년 구간 유지율이 87.2% 가 아니라 98.8% 로 보이는 그 오해다.

          두 줄 고정. 문장으로 풀지 않는다(리뷰 지적).
        */}
        <p className="text-base text-muted-foreground/80">
          의존자 {shares.total.toLocaleString()} 중
          <br />
          {shares.active.toLocaleString()} 판정
          <br />
          {/* 이름은 CATEGORIES 에서만 읽는다 — 그 낱말은 결정의 산물이라(위 주석) 바뀔 수 있고,
              여기 따로 적어 두면 막대와 캡션이 같은 수를 다른 이름으로 부르게 된다. */}
          <span className="text-muted-foreground/70">
            {(shares.total - shares.active).toLocaleString()} {CATEGORIES[3].label}
          </span>
        </p>
      </div>
      <dl className="flex w-full max-w-64 flex-col gap-1.5">
        <RatioRow fill={CATEGORIES[0].fill} label={CATEGORIES[0].label} pct={shares.retainedPct} />
        <RatioRow
          fill={CATEGORIES[1].fill}
          label={CATEGORIES[1].label}
          pct={shares.inflowAdoptedPct}
        />
        <RatioRow fill={CATEGORIES[2].fill} label={CATEGORIES[2].label} pct={shares.outflowPct} />
      </dl>
    </div>
  )
}

function RatioRow({ fill, label, pct }: { fill: string; label: string; pct: number }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="h-2.5 w-2.5 shrink-0 rounded-[3px]"
        style={{ background: fill }}
        aria-hidden
      />
      <dt className="text-base text-muted-foreground">{label}</dt>
      <dd className="ml-auto font-mono text-base text-muted-foreground tabular-nums">
        {pct.toFixed(1)}%
      </dd>
    </div>
  )
}

/**
 * 한 줄 막대. `sub` 는 바로 위 범주를 쪼갠 줄이다 (S15P21A506-431) — 들여쓰고 가늘게 그려
 * **다섯 번째 범주가 아니라 한 칸의 분해**라는 것이 형태로 보이게 한다. 같은 `max` 스케일을
 * 쓰므로 하위 줄들의 길이를 더하면 위 줄의 길이가 되고, **위 줄을 넘는 일은 없다.**
 */
function BarRow({
  label,
  fill,
  value,
  dataStatus,
  max,
  sub = false,
}: {
  label: string
  fill: string
  value: number | null
  dataStatus: TransitionDataStatus
  max: number
  sub?: boolean
}) {
  const isPlaceholder = dataStatus === 'OUT_OF_SCOPE' || dataStatus === 'NOT_COMPUTED'
  /**
   * 값이 있는데 막대가 사라지지 않도록 최소 폭을 준다. **하위 줄에는 주지 않는다** — 순위가
   * 크게 차이 나는 패키지를 나란히 놓으면 작은 쪽은 부모도 하위도 전부 이 바닥값에 걸려,
   * 하위 둘을 더한 길이가 부모보다 길어진다(부모 2% · 하위 2%+2%). 그러면 분해가 아니라
   * 더 큰 별도 범주로 보인다. 하위는 정확한 비율로만 그리고, 수는 오른쪽에 그대로 찍힌다.
   */
  const minWidth = sub ? 0 : MIN_BAR_WIDTH
  const width = isPlaceholder
    ? PLACEHOLDER_WIDTH
    : value !== null && max > 0
      ? Math.max((value / max) * 100, value > 0 ? minWidth : 0)
      : 0

  return (
    <div className={cn('grid grid-cols-[92px_1fr_64px] items-center gap-2', sub && '-mt-0.5')}>
      <span
        className={cn(
          'text-base whitespace-nowrap text-muted-foreground',
          sub && 'pl-3 text-muted-foreground/70',
        )}
      >
        {label}
      </span>
      <span
        className={cn(
          'overflow-hidden rounded-sm',
          sub ? 'h-1.5' : 'h-2.5',
          dataStatus === 'NOT_COMPUTED' ? 'border border-dashed bg-transparent' : 'bg-muted',
        )}
      >
        {dataStatus === 'OUT_OF_SCOPE' ? (
          // CSS `background: url(#svg-pattern)`은 SVG 페인트 서버를 HTML 배경으로
          // 참조하는 비표준 방식이라 Chrome에서 렌더링되지 않는다(실기기 확인함,
          // `ShareBars`의 기존 `UNRESOLVED_FILL` 사용도 같은 문제를 잠재적으로 안고
          // 있으나 현재 데이터에 UNRESOLVED 조각이 없어 아직 드러나지 않았을 뿐이다).
          // 그래서 `fill` 속성으로 직접 참조되는 `<rect>`로 그린다 — 이건 표준이라
          // 크로스브라우저로 확실히 동작한다.
          <svg width="100%" height="100%" viewBox="0 0 100 10" preserveAspectRatio="none">
            <rect width={width} height="10" rx="2" fill="url(#pk-hatch)" />
          </svg>
        ) : dataStatus !== 'NOT_COMPUTED' ? (
          <span
            className={cn('block h-full rounded-sm', sub && 'opacity-60')}
            style={{ width: `${width}%`, background: fill }}
          />
        ) : null}
      </span>
      <span
        className={cn(
          'text-right font-mono text-base tabular-nums',
          sub ? 'text-muted-foreground/70' : 'text-muted-foreground',
        )}
      >
        {isPlaceholder ? '—' : (value ?? 0).toLocaleString()}
      </span>
    </div>
  )
}
