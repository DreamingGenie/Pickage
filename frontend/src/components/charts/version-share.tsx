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

function HatchDef() {
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
}: {
  groups: ShareGroup[]
  size?: number
  className?: string
  ariaLabel: string
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
      fill: fillOf(g.label, i),
    }
  })

  const top = groups.reduce((a, b) => (b.share > a.share ? b : a), groups[0])

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
              'font-mono text-[11px]',
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
          <span className="text-right font-mono text-[11px] text-muted-foreground tabular-nums">
            {Math.round(g.share * 100)}%
          </span>
        </div>
      ))}
    </div>
  )
}
