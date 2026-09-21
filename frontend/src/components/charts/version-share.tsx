import { donutArc } from '@/components/charts/geometry'
import { SHARE_FILLS, UNRESOLVED_FILL } from '@/components/charts/tokens'
import { cn } from '@/lib/utils'

export interface ShareGroup {
  label: string
  share: number
}

/** 해석할 수 없는 버전 조건. 임의 주버전에 편입하지 않는다(구상안 5.4). */
export const UNRESOLVED = 'UNRESOLVED'

const fillOf = (label: string, i: number) =>
  label === UNRESOLVED ? UNRESOLVED_FILL : SHARE_FILLS[i % SHARE_FILLS.length]

/**
 * export한다 — `transition-bars.tsx`가 같은 "해석 불가/집계 대상 아님" 빗금을 재사용한다.
 * 같은 페이지(생태계 탭)에 `id="pk-hatch"` 패턴을 두 번 정의하면 DOM id가 충돌하므로,
 * 새로 만들지 않고 이 정의 하나만 쓴다.
 */
export function HatchDef() {
  return (
    <defs>
      <pattern
        id="pk-hatch"
        width="5"
        height="5"
        patternUnits="userSpaceOnUse"
        patternTransform="rotate(45)"
      >
        <rect width="5" height="5" fill="var(--muted)" />
        <line
          x1="0"
          y1="0"
          x2="0"
          y2="5"
          stroke="var(--muted-foreground)"
          strokeWidth="1.4"
          strokeOpacity="0.55"
        />
      </pattern>
    </defs>
  )
}

/**
 * Version Share 도넛 (IA 8.5).
 * UNRESOLVED 는 색이 아니라 빗금으로 갈라서 "해석 못 한 몫"임을 형태로 알린다.
 */
export function ShareDonut({
  groups,
  size = 116,
  className,
  ariaLabel,
  centerOverride,
  fills,
}: {
  groups: ShareGroup[]
  size?: number
  className?: string
  ariaLabel: string
  /**
   * 가운데 글자를 "가장 큰 몫"이 아니라 정해진 항목으로 고정한다.
   *
   * 이탈 사유 도넛이 이걸 쓴다 — "대체 없이 제거"가 이 지표의 결론이라 몫이 절반을 안 넘어도
   * 항상 가운데에 둬야 한다(구상안 §RemovalBars). 없으면 기존처럼 가장 큰 몫을 고른다.
   */
  centerOverride?: { label: string; share: number }
  /**
   * 자리(index)별 색을 지정한다. 없으면 기존처럼 `SHARE_FILLS`를 순서대로 쓴다.
   *
   * 이탈 사유 도넛이 이걸 쓴다 — 두 조각뿐인데 `SHARE_FILLS[0]`·`[1]`을 그대로 쓰면 대비가
   * 약해 범례 없이는 구분이 어렵다. 막대였을 때부터 `[0]`·`[2]`를 써 온 배색을 그대로 옮긴다.
   */
  fills?: string[]
}) {
  const cx = size / 2
  const cy = size / 2
  const rOuter = size / 2 - 2
  const rInner = rOuter * 0.62

  // 조각 시작 각도는 앞선 몫의 합. 계열이 많아야 대여섯이라 매번 더해도 된다.
  const arcs = groups.map((g, i) => {
    const start = groups.slice(0, i).reduce((sum, x) => sum + x.share, 0)
    return {
      ...g,
      d: donutArc(cx, cy, rOuter, rInner, start, start + g.share),
      fill: fills ? fills[i % fills.length] : fillOf(g.label, i),
    }
  })

  const top = centerOverride ?? groups.reduce((a, b) => (b.share > a.share ? b : a), groups[0])

  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={`0 0 ${size} ${size}`}
      width={size}
      height={size}
      className={cn('shrink-0', className)}
    >
      <HatchDef />
      {arcs.map((a) => (
        <path key={a.label} d={a.d} fill={a.fill} stroke="var(--background)" strokeWidth="1.5" />
      ))}
      <text
        x={cx}
        y={cy - 1}
        textAnchor="middle"
        fontSize="15"
        fontWeight="600"
        fill="var(--foreground)"
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        {Math.round(top.share * 100)}%
      </text>
      <text x={cx} y={cy + 12} textAnchor="middle" fontSize="9" fill="var(--muted-foreground)">
        {top.label}
      </text>
    </svg>
  )
}

/** 계열 막대 + 수치. 도넛 오른쪽에 붙는다(IA 8.5). */
export function ShareBars({ groups, className }: { groups: ShareGroup[]; className?: string }) {
  const max = Math.max(...groups.map((g) => g.share))
  return (
    <div className={cn('flex min-w-0 flex-1 flex-col gap-1.5', className)}>
      <svg width="0" height="0" aria-hidden className="absolute">
        <HatchDef />
      </svg>
      {groups.map((g, i) => (
        <div key={g.label} className="grid grid-cols-[62px_1fr_38px] items-center gap-2">
          <span
            className={cn(
              'font-mono text-base',
              g.label === UNRESOLVED ? 'text-muted-foreground' : 'text-foreground',
            )}
          >
            {g.label === UNRESOLVED ? '해석 불가' : g.label}
          </span>
          <span className="h-2.5 overflow-hidden rounded-sm bg-muted">
            <span
              className="block h-full rounded-sm"
              style={{
                width: `${(g.share / max) * 100}%`,
                background: fillOf(g.label, i),
              }}
            />
          </span>
          <span className="text-right font-mono text-base text-muted-foreground tabular-nums">
            {Math.round(g.share * 100)}%
          </span>
        </div>
      ))}
    </div>
  )
}
