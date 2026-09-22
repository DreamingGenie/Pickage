import {
  CircleAlertIcon,
  CircleHelpIcon,
  DownloadIcon,
  MoveRightIcon,
  TrendingDownIcon,
  TrendingUpIcon,
  PackageCheckIcon,
  ShieldAlertIcon,
  StarIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'

import { compact } from '@/components/charts/geometry'
import {
  DOWNLOAD_TIER_BOUNDS,
  DOWNLOAD_TIER_LABEL,
  TREND_LABEL,
  downloadTierOf,
  type DownloadTier,
  type Trend,
  type TrendDirection,
} from '@/routes/report/ecosystem/insights'
import { ToneBadge, type Tone as LabelTone } from '@/components/common/tone-badge'
import type { PackageCardModel } from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

/**
 * 관측 뱃지 타일.
 *
 * 전부 관측 사실만 적는다. "건강함" 같은 판정 문구를 쓰지 않는다.
 * 색은 보조 신호일 뿐이고 값과 라벨이 항상 문자로 나온다.
 *
 * **null 은 0 이 아니다.** 스냅샷 미수신은 "집계 대기 중"으로 적고 점선 테두리로
 * 구분한다 — 없는 것과 못 본 것을 같은 모양으로 그리면 안 된다(명세 0.5).
 */

type Tone = 'neutral' | 'notable' | 'unknown'

const TONE: Record<Tone, { tile: string; ring: string; icon: string }> = {
  neutral: {
    tile: 'border-border',
    ring: 'bg-slate-100',
    icon: 'text-slate-600',
  },
  notable: {
    tile: 'border-border',
    ring: 'bg-amber-100',
    icon: 'text-amber-700',
  },
  unknown: {
    tile: 'border-dashed',
    ring: 'bg-muted',
    icon: 'text-muted-foreground',
  },
}

function BadgeTile({
  icon,
  value,
  label,
  delta,
  tone = 'neutral',
  title,
}: {
  icon: ReactNode
  value: string
  label: string
  /** 직전 스냅샷 대비 변량. `null` 이면 첫 스냅샷이라 비교할 값이 없다 */
  delta?: number | null
  tone?: Tone
  title?: string
}) {
  const t = TONE[tone]
  /*
    아이콘을 위에 얹지 않고 **왼쪽에 둔다.** 세로로 쌓으면 타일이 높아지는데 폭은 그대로라
    긴 라벨이 여전히 접힌다. 가로로 두면 남는 폭을 글자가 쓴다.
  */
  return (
    <div
      title={title}
      className={cn('flex items-center gap-3 rounded-xl border bg-background px-3 py-3', t.tile)}
    >
      <span className={cn('grid size-9 shrink-0 place-items-center rounded-full', t.ring, t.icon)}>
        {icon}
      </span>
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="flex items-baseline gap-1.5">
          <span
            className={cn(
              'leading-none font-semibold tabular-nums',
              tone === 'unknown' && 'font-medium text-muted-foreground',
            )}
          >
            {value}
          </span>
          {tone !== 'unknown' && <DeltaMark delta={delta} />}
        </span>
        <span className="leading-snug text-muted-foreground">{label}</span>
      </span>
    </div>
  )
}

/**
 * 변량 표시. 값 **바로 옆**에 붙는다.
 *
 * <p>예전에는 라벨 뒤에 " · 직전 주 +12" 로 달았다. 값과 변량이 서로 다른 줄에 있으면
 * 눈이 두 번 움직이고, 라벨이 길어져 좁은 타일에서 접혔다.
 *
 * <p>색은 **방향만** 말한다 — 오름은 붉게, 내림은 푸르게. 시세판과 같은 약속이라
 * 설명 없이 읽힌다. 좋고 나쁨이 아니다: 미해결 이슈가 늘어도 붉게 나온다. 이 파일의
 * 원칙대로 판정은 하지 않고 관측한 방향만 적는다.
 *
 * <p>색에만 기대지 않는다. 부호(`+`·`−`)가 항상 함께 나가므로 색을 못 봐도 읽힌다.
 *
 * <p>`null` 은 첫 스냅샷이라 **비교할 직전 값이 없다**는 뜻이다. 0 과 다르므로 아무것도
 * 그리지 않는다. 0 은 "안 변했다" 라 그대로 적는다.
 */
function DeltaMark({ delta }: { delta?: number | null }) {
  if (delta === null || delta === undefined) return null
  const tone =
    delta > 0
      ? 'text-rose-600 dark:text-rose-400'
      : delta < 0
        ? 'text-blue-600 dark:text-blue-400'
        : 'text-muted-foreground'
  const sign = delta > 0 ? '+' : delta < 0 ? '−' : '±'
  return (
    <span
      className={cn('text-base leading-none font-medium tabular-nums', tone)}
      title={`지난번에 모은 값보다 ${sign}${Math.abs(delta).toLocaleString()}`}
    >
      {sign}
      {compact(Math.abs(delta))}
    </span>
  )
}

const PENDING = '모으는 중'

/**
 * 값이 없는 자리를 채우는 안내.
 *
 * <p>차트나 도넛이 들어갈 **넓은 자리**에 쓴다. 한 줄짜리 값은 위 `BadgeTile` 의
 * `tone="unknown"` 이 이미 그 일을 한다 — 같은 화면에 빈 자리 모양이 둘이면 사용자가
 * 둘을 다른 뜻으로 읽는다.
 *
 * <p>테두리를 점선으로, 바탕을 반투명하게 둔다. 값이 있는 자리와 **모양으로** 구분되어야
 * 색을 못 보는 사람도 "여기는 비었다" 를 안다(명세 0.5 — 없는 것과 못 본 것을 같은
 * 모양으로 그리지 않는다). 글자 자체는 흐리게 하지 않는다. 읽으라고 쓴 문장이다.
 */
export function EmptyPanel({
  message,
  hint,
  className,
}: {
  message: string
  hint?: string
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed bg-muted/40 px-4 py-7 text-center',
        className,
      )}
    >
      <CircleAlertIcon className="size-7 text-muted-foreground/70" aria-hidden />
      <p className="text-base leading-snug text-muted-foreground">{message}</p>
      {hint && <p className="text-base leading-snug text-muted-foreground/70">{hint}</p>}
    </div>
  )
}

/** 한 줄짜리 값이 비었을 때. 위 네 타일과 같은 모양을 쓴다. */
export function MissingTile({ label, title }: { label: string; title?: string }) {
  return (
    <BadgeTile
      icon={<CircleHelpIcon className="size-[18px]" />}
      value="값 없음"
      label={label}
      tone="unknown"
      title={title}
    />
  )
}

export function ObservationBadges({
  model,
  className,
}: {
  model: PackageCardModel
  className?: string
}) {
  return (
    /*
      **2열 고정이다.** 예전에는 넓어지면 4열이 됐는데, 카드가 우측 열로 가고 글자가
      16px 로 커지면서 타일 하나에 90px 남짓만 남았다. "최신 버전 폐기 표시" 같은 라벨이
      두 줄로 접히고 값과 라벨이 서로 밀려난다.

      2열이면 타일이 두 배 넓어져 라벨이 한 줄에 들어간다. 세로로 한 줄 늘어나는 대신
      가로로 안 접힌다 — 읽는 사람에게는 그쪽이 낫다.
    */
    <div className={cn('grid grid-cols-2 gap-2.5', className)}>
      <DownloadsTile downloads={model.downloads} />
      <StarsTile stars={model.stars} delta={model.starsDelta} repoUrl={model.repoUrl} />
      <IssuesTile count={model.openIssues} delta={model.openIssuesDelta} repoUrl={model.repoUrl} />
      <DeprecationTile deprecated={model.isDeprecated} />
    </div>
  )
}

/**
 * 주간 다운로드.
 *
 * 명세 §3 — 이 값은 **직전 7일 합계**다. 라벨을 "주간"으로 고정한다.
 * 일별로 오해되면 규모 감각이 7배 틀어진다.
 */
function DownloadsTile({ downloads }: { downloads: number | null }) {
  if (downloads === null) {
    return (
      <BadgeTile
        icon={<CircleHelpIcon className="size-[18px]" />}
        value={PENDING}
        label="주간 다운로드"
        tone="unknown"
        title="패키지는 있지만 아직 모은 값이 없어요"
      />
    )
  }
  return (
    <BadgeTile
      icon={<DownloadIcon className="size-[18px]" />}
      value={compact(downloads)}
      label="주간 다운로드"
      title="최근 7일 동안 내려받은 횟수 · npm 공식 자료"
    />
  )
}

function StarsTile({
  stars,
  delta,
  repoUrl,
}: {
  stars: number | null
  delta: number | null
  repoUrl: string | null
}) {
  if (stars === null) {
    return (
      <BadgeTile
        icon={<CircleHelpIcon className="size-[18px]" />}
        value={repoUrl ? PENDING : '알 수 없음'}
        label="저장소 별"
        tone="unknown"
        title={repoUrl ? '아직 모은 값이 없어요' : '저장소 주소가 없어서 알 수 없어요'}
      />
    )
  }
  return (
    <BadgeTile
      icon={<StarIcon className="size-[18px]" />}
      value={compact(stars)}
      delta={delta}
      label="저장소 별"
      title="가장 최근에 모은 값이에요"
    />
  )
}

/**
 * 열린 이슈.
 *
 * **등록 건수가 아니라 현재 열려 있는 수**다. 늘었다고 나쁜 것도, 줄었다고 좋은 것도
 * 아니어서(닫아서 줄 수도, 관심이 식어서 줄 수도 있다) 방향에 색을 입히지 않는다.
 * 0건과 미확인을 가르는 것이 이 타일의 핵심이다.
 */
function IssuesTile({
  count,
  delta,
  repoUrl,
}: {
  count: number | null
  delta: number | null
  repoUrl: string | null
}) {
  if (count === null) {
    return (
      <BadgeTile
        icon={<CircleHelpIcon className="size-[18px]" />}
        value={repoUrl ? PENDING : '알 수 없음'}
        label="열린 이슈"
        tone="unknown"
        title={repoUrl ? '아직 모은 값이 없어요' : '저장소 주소가 없어서 알 수 없어요'}
      />
    )
  }
  if (count === 0) {
    return (
      <BadgeTile
        icon={<CircleAlertIcon className="size-[18px]" />}
        value="0건"
        label="열린 이슈"
        tone="unknown"
        title="지금 열려 있는 이슈가 없다는 뜻이에요. 문제가 있다는 뜻은 아니에요"
      />
    )
  }
  return (
    <BadgeTile
      icon={<CircleAlertIcon className="size-[18px]" />}
      value={`${count.toLocaleString()}건`}
      delta={delta}
      label="열린 이슈"
    />
  )
}

/**
 * 폐기 표시.
 *
 * 버전 단위 값이라 "패키지가 폐기됐다"고 말하지 않고
 * "최신 버전에 표시가 있는지"만 적는다. 표시가 붙은 시점은 알 수 없다 —
 * 과거 버전의 폐기 여부를 스냅샷으로 받지 않기 때문이다.
 */
function DeprecationTile({ deprecated }: { deprecated: boolean }) {
  if (deprecated) {
    return (
      <BadgeTile
        icon={<ShieldAlertIcon className="size-[18px]" />}
        value="있음"
        label="최신 버전 지원 종료 표시"
        tone="notable"
        title="만든 사람이 최신 버전에 '더 이상 쓰지 말라(deprecated)'고 표시했어요. 언제 붙였는지는 알 수 없어요"
      />
    )
  }
  return (
    <BadgeTile
      icon={<PackageCheckIcon className="size-[18px]" />}
      value="없음"
      label="최신 버전 지원 종료 표시"
    />
  )
}

/* ── 새 카드 구성: 다운로드 수준 · 3개월 추세 · 열린 이슈 ─────────────────────── */

/**
 * 카드의 한눈 정보. 숫자를 나열하지 않고 **한마디 판단**을 앞세운다 — "높은 편", "증가".
 * 판단 기준은 `insights.ts` 한 곳에 있다. 원래 숫자는 옆에 작게 둔다.
 */
export function InsightBadges({
  model,
  downloadsTrend,
  dependentsTrend,
  dependentsLabel,
  className,
}: {
  model: PackageCardModel
  downloadsTrend: Trend | null
  dependentsTrend: Trend | null
  /** 의존 등록 수 용어(terms.tsx) */
  dependentsLabel: string
  className?: string
}) {
  const tier = downloadTierOf(model.downloads)
  return (
    <div className={cn('grid grid-cols-2 gap-2.5', className)}>
      {tier === null ? (
        <BadgeTile
          icon={<CircleHelpIcon className="size-[18px]" />}
          value={PENDING}
          label="다운로드 수준"
          tone="unknown"
          title="패키지는 있지만 아직 모은 값이 없어요"
        />
      ) : (
        <div
          className="flex items-center gap-3 rounded-xl border bg-background px-3 py-3"
          title={`주간 다운로드 ${DOWNLOAD_TIER_BOUNDS.high.toLocaleString()}회 이상이면 높은 편, ${DOWNLOAD_TIER_BOUNDS.low.toLocaleString()}회 미만이면 낮은 편이에요`}
        >
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-muted">
            <DownloadIcon className="size-[18px]" />
          </span>
          <span className="flex min-w-0 flex-col items-start gap-1">
            <ToneBadge tone={TIER_TONE[tier]}>{DOWNLOAD_TIER_LABEL[tier]}</ToneBadge>
            <span className="leading-snug text-muted-foreground">
              주간 {compact(model.downloads as number)}회
            </span>
          </span>
        </div>
      )}
      <IssuesTile count={model.openIssues} delta={model.openIssuesDelta} repoUrl={model.repoUrl} />
      <div
        className="col-span-2 flex flex-col gap-2 rounded-xl border bg-background px-3 py-3"
        title="최근 값과 3개월 전 값을 비교해요. 10% 넘게 오르면 증가, 10% 넘게 내리면 감소예요"
      >
        <span className="flex items-baseline justify-between gap-2">
          <span className="font-semibold">추세</span>
          <span className="text-sm text-muted-foreground">3개월 전과 비교</span>
        </span>
        <TrendRow label="다운로드" trend={downloadsTrend} />
        <TrendRow label={dependentsLabel} trend={dependentsTrend} />
      </div>
    </div>
  )
}

const TREND_ICON = { up: TrendingUpIcon, flat: MoveRightIcon, down: TrendingDownIcon } as const

/**
 * 라벨 색. 색은 거들 뿐이고 뜻은 글자가 말한다(IA 1-13).
 * 늘었다·많다는 초록, 그대로·보통은 회색, 줄었다·적다는 주황 — 주황은 "나쁘다" 가 아니라 "살펴볼 만하다" 는 뜻이다.
 */
const TIER_TONE = { high: 'positive', mid: 'neutral', low: 'down' } as const satisfies Record<
  DownloadTier,
  LabelTone
>
const TREND_TONE = { up: 'positive', flat: 'neutral', down: 'down' } as const satisfies Record<
  TrendDirection,
  LabelTone
>

/** 추세 한 줄. 방향은 아이콘·글자·부호로 함께 알린다 — 색만으로 알리지 않는다(IA 1-13). */
function TrendRow({ label, trend }: { label: string; trend: Trend | null }) {
  if (trend === null) {
    return (
      <span className="flex items-center justify-between gap-2 text-muted-foreground">
        <span>{label}</span>
        <span className="text-sm">3개월 치 자료가 아직 없어요</span>
      </span>
    )
  }
  const Icon = TREND_ICON[trend.direction]
  const pct = Math.round(trend.rate * 100)
  return (
    <span className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="flex items-center gap-1.5 tabular-nums">
        <ToneBadge tone={TREND_TONE[trend.direction]} icon={<Icon aria-hidden />}>
          {TREND_LABEL[trend.direction]}
        </ToneBadge>
        <span className="text-muted-foreground">
          {pct > 0 ? '+' : pct < 0 ? '−' : '±'}
          {Math.abs(pct)}%
        </span>
      </span>
    </span>
  )
}
