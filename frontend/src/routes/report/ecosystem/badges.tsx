import {
  ActivityIcon,
  CircleHelpIcon,
  PackageCheckIcon,
  ShieldAlertIcon,
  StarIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'

import { compact } from '@/components/charts/geometry'
import type { PackageCardModel } from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

/**
 * 관측 뱃지 타일.
 *
 * 전부 관측 사실만 적는다. "건강함" 같은 판정 문구를 쓰지 않는다(IA 1.10).
 * 색은 보조 신호일 뿐이고 값과 라벨이 항상 문자로 나온다(IA 1.11).
 * 미확인은 실패색을 쓰지 않고 점선 테두리로 구분한다.
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
  tone = 'neutral',
  title,
}: {
  icon: ReactNode
  value: string
  label: string
  tone?: Tone
  title?: string
}) {
  const t = TONE[tone]
  return (
    <div
      title={title}
      className={cn(
        'flex flex-col items-center gap-2 rounded-xl border bg-background px-2 py-4 text-center',
        t.tile,
      )}
    >
      <span className={cn('grid size-9 place-items-center rounded-full', t.ring, t.icon)}>
        {icon}
      </span>
      <span className="flex flex-col gap-0.5">
        <span
          className={cn(
            'text-[13px] leading-none font-semibold tabular-nums',
            tone === 'unknown' && 'font-medium text-muted-foreground',
          )}
        >
          {value}
        </span>
        <span className="text-[10.5px] leading-tight text-muted-foreground">{label}</span>
      </span>
    </div>
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
    <div className={cn('grid grid-cols-3 gap-2.5', className)}>
      <StarsTile stars={model.stars} delta={model.starsDelta52w} />
      <IssueTile count={model.recentIssues12w} scope={model.repositoryScope} />
      <DeprecationTile
        deprecated={model.deprecatedLatest}
        observedAt={model.deprecationObservedAt}
      />
    </div>
  )
}

function StarsTile({ stars, delta }: { stars: number | null; delta: number | null }) {
  if (stars === null) {
    return (
      <BadgeTile
        icon={<CircleHelpIcon className="size-[18px]" />}
        value="미확인"
        label="저장소 별"
        tone="unknown"
        title="저장소 연결이 검증되지 않았습니다"
      />
    )
  }
  return (
    <BadgeTile
      icon={<StarIcon className="size-[18px]" />}
      value={compact(stars)}
      label={
        delta === null
          ? '저장소 별'
          : `저장소 별 · 52주 ${delta >= 0 ? '+' : '−'}${compact(Math.abs(delta))}`
      }
      title="Projects 스냅샷 기준"
    />
  )
}

/**
 * 이슈 활동. 등록 건수만 적는다.
 * 0건과 미확인을 가르는 게 이 타일의 핵심이다 — 없는 것과 못 본 것은 다르다.
 */
function IssueTile({
  count,
  scope,
}: {
  count: number | null
  scope: PackageCardModel['repositoryScope']
}) {
  if (count === null || scope === 'UNVERIFIED') {
    return (
      <BadgeTile
        icon={<CircleHelpIcon className="size-[18px]" />}
        value="미확인"
        label="저장소 미검증"
        tone="unknown"
      />
    )
  }
  if (count === 0) {
    return (
      <BadgeTile
        icon={<ActivityIcon className="size-[18px]" />}
        value="0건"
        label="최근 12주 이슈"
        tone="unknown"
        title="등록이 없다는 관측이며, 문제가 있다는 뜻이 아닙니다"
      />
    )
  }
  return (
    <BadgeTile
      icon={<ActivityIcon className="size-[18px]" />}
      value={`${count}건`}
      label={scope === 'REPOSITORY_WIDE' ? '최근 12주 · 저장소 전체' : '최근 12주 이슈'}
    />
  )
}

/**
 * 폐기 표시. 버전 단위 값이라 "패키지가 폐기됐다"고 말하지 않고
 * "최신 안정 버전에 표시가 있는지"만 적는다. 시점은 과거 스냅샷이 없어 알 수 없다.
 */
function DeprecationTile({
  deprecated,
  observedAt,
}: {
  deprecated: boolean | null
  observedAt: string | null
}) {
  if (deprecated === null) {
    return (
      <BadgeTile
        icon={<CircleHelpIcon className="size-[18px]" />}
        value="미확인"
        label="폐기 표시"
        tone="unknown"
      />
    )
  }
  if (deprecated) {
    return (
      <BadgeTile
        icon={<ShieldAlertIcon className="size-[18px]" />}
        value="있음"
        label="최신 버전 폐기 표시"
        tone="notable"
        title={observedAt ? `${observedAt} 관측` : undefined}
      />
    )
  }
  return (
    <BadgeTile
      icon={<PackageCheckIcon className="size-[18px]" />}
      value="없음"
      label="최신 버전 폐기 표시"
      title={observedAt ? `${observedAt} 관측` : undefined}
    />
  )
}
