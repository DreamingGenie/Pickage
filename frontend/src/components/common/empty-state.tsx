import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * 보여 줄 것이 없는 자리. 빈 칸으로 두지 않고 **왜 비었는지**와 **다음에 할 일**을 말한다.
 *
 *   title       지금 상태 — "아직 비교한 기능이 없어요"
 *   description 이유와 방법 — "위 버튼을 누르면 1분쯤 걸려 정리해 드려요"
 *   actions     다음 행동 버튼
 *
 * 오류(서버가 실패함)는 여기가 아니라 `Notice tone="error"` 를 쓴다. 비어 있는 것과 실패한 것은
 * 사용자가 할 일이 다르다.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  actions,
  className,
}: {
  icon?: LucideIcon
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-3 rounded-2xl border border-dashed bg-card px-6 py-12 text-center',
        className,
      )}
    >
      {Icon && (
        <span className="grid size-11 place-items-center rounded-full bg-brand-soft text-primary">
          <Icon aria-hidden className="size-5" />
        </span>
      )}
      <p className="text-lg font-semibold text-foreground">{title}</p>
      {description && (
        <p className="max-w-md text-base leading-relaxed text-balance text-muted-foreground">
          {description}
        </p>
      )}
      {actions && (
        <div className="mt-2 flex flex-wrap items-center justify-center gap-2">{actions}</div>
      )}
    </div>
  )
}
