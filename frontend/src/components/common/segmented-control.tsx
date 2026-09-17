import { cn } from '@/lib/utils'

/**
 * 배타적 선택 토글. `ecosystem-toolbar.tsx`의 "표시 간격"에서 처음 만들었고,
 * 지표 카드의 축·표시 모드 토글(`metric-chart.tsx`)에서도 같은 모양을 쓰게 되어 공용화했다
 * — 두 군데서 각자 구현하면 스타일이 갈린다.
 */
export function SegmentedControl({
  label,
  options,
  value,
  onChange,
  className,
}: {
  label: string
  options: { key: string; label: string }[]
  value: string
  onChange: (key: string) => void
  className?: string
}) {
  return (
    <div
      className={cn('flex gap-0.5 rounded-md bg-muted p-0.5', className)}
      role="group"
      aria-label={label}
    >
      {options.map((o) => {
        const active = value === o.key
        return (
          <button
            key={o.key}
            type="button"
            onClick={() => onChange(o.key)}
            aria-pressed={active}
            className={cn(
              'rounded-[5px] px-2 py-1 text-base transition-colors',
              active
                ? 'bg-background font-medium text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
