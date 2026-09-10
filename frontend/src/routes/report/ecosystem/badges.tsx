import {
  CircleAlertIcon,
  CircleHelpIcon,
  DownloadIcon,
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
        <span
          className={cn(
            'leading-none font-semibold tabular-nums',
            tone === 'unknown' && 'font-medium text-muted-foreground',
          )}
        >
          {value}
        </span>
        <span className="leading-snug text-muted-foreground">{label}</span>
      </span>
    </div>
  )
}

/** 증감 꼬리표. null 이면 아무것도 붙이지 않는다 — 첫 스냅샷이라 직전 값이 없는 것이다. */
function deltaSuffix(delta: number | null): string {
  if (delta === null || delta === 0) return ''
  return ` · 직전 주 ${delta > 0 ? '+' : '−'}${compact(Math.abs(delta))}`
}

const PENDING = '집계 대기'

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
        title="패키지는 있으나 아직 스냅샷이 없습니다"
      />
    )
  }
  return (
    <BadgeTile
      icon={<DownloadIcon className="size-[18px]" />}
      value={compact(downloads)}
      label="주간 다운로드"
      title="직전 7일 합계 · npm 공식 자료"
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
        value={repoUrl ? PENDING : '미확인'}
        label="저장소 별"
        tone="unknown"
        title={repoUrl ? '아직 스냅샷이 없습니다' : '저장소 주소가 없어 관측할 수 없습니다'}
      />
    )
  }
  return (
    <BadgeTile
      icon={<StarIcon className="size-[18px]" />}
      value={compact(stars)}
      label={`저장소 별${deltaSuffix(delta)}`}
      title="최신 스냅샷 기준"
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
        value={repoUrl ? PENDING : '미확인'}
        label="열린 이슈"
        tone="unknown"
        title={repoUrl ? '아직 스냅샷이 없습니다' : '저장소 주소가 없어 관측할 수 없습니다'}
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
        title="열린 이슈가 없다는 관측이며, 문제가 있다는 뜻이 아닙니다"
      />
    )
  }
  return (
    <BadgeTile
      icon={<CircleAlertIcon className="size-[18px]" />}
      value={`${count.toLocaleString()}건`}
      label={`열린 이슈${deltaSuffix(delta)}`}
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
        label="최신 버전 폐기 표시"
        tone="notable"
        title="표시가 붙은 시점은 알 수 없습니다"
      />
    )
  }
  return (
    <BadgeTile
      icon={<PackageCheckIcon className="size-[18px]" />}
      value="없음"
      label="최신 버전 폐기 표시"
    />
  )
}
