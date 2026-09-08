import { Badge } from '@/components/ui/badge'
import type { StatusLevel } from '@/api/types'
import { cn } from '@/lib/utils'

/**
 * 미해결: warn/err 색상은 디자인 확정값이 아니라 ok 기준으로 파생시킨 값이다.
 * 디자이너 확인 후 아래 map만 교체하면 된다.
 */
const STYLE: Record<StatusLevel, string> = {
  ok: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  warn: 'bg-amber-50 text-amber-700 border-amber-200',
  err: 'bg-red-50 text-red-700 border-red-200',
}

const LABEL: Record<StatusLevel, string> = {
  ok: '양호',
  warn: '주의',
  err: '위험',
}

export function StatusBadge({
  status,
  label,
  className,
}: {
  status: StatusLevel
  label?: string
  className?: string
}) {
  return (
    <Badge variant="outline" className={cn(STYLE[status], className)}>
      {label ?? LABEL[status]}
    </Badge>
  )
}
