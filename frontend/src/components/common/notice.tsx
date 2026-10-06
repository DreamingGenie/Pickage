import {
  CircleAlertIcon,
  CircleCheckIcon,
  InfoIcon,
  TriangleAlertIcon,
  type LucideIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * 한 줄짜리 안내 상자 — **무슨 일인지 + 이제 뭘 하면 되는지**를 함께 말한다.
 *
 * 오류를 알릴 때 "실패했습니다" 로 끝내지 않는다. `title` 에 일어난 일을, `children` 에 이유를,
 * `action` 에 다음 행동(버튼·링크)을 둔다. 이유를 모르면 "잠시 뒤 다시 해 보세요" 처럼
 * 사용자가 할 수 있는 일을 적는다.
 *
 * 색만으로 뜻을 전하지 않도록 톤마다 아이콘을 붙인다(IA 1-13). 오류는 `role="alert"` 로
 * 바로 읽히고, 나머지는 `role="status"` 로 흐름을 끊지 않는다.
 */
export type NoticeTone = 'info' | 'success' | 'warn' | 'error'

const STYLE: Record<NoticeTone, { box: string; icon: LucideIcon; iconClass: string }> = {
  info: { box: 'bg-brand-soft', icon: InfoIcon, iconClass: 'text-primary' },
  success: {
    box: 'bg-tone-positive',
    icon: CircleCheckIcon,
    iconClass: 'text-tone-positive-foreground',
  },
  warn: { box: 'bg-tone-down', icon: TriangleAlertIcon, iconClass: 'text-tone-down-foreground' },
  error: { box: 'bg-tone-danger', icon: CircleAlertIcon, iconClass: 'text-tone-danger-foreground' },
}

export function Notice({
  tone = 'info',
  title,
  action,
  icon,
  className,
  children,
}: {
  tone?: NoticeTone
  title: ReactNode
  /** 톤의 기본 아이콘 대신 쓸 아이콘 */
  icon?: LucideIcon
  /** 다음 행동. 버튼이나 링크를 넘긴다. */
  action?: ReactNode
  className?: string
  children?: ReactNode
}) {
  const s = STYLE[tone]
  const Icon = icon ?? s.icon
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn('flex items-start gap-3 rounded-xl px-4 py-3.5', s.box, className)}
    >
      <Icon aria-hidden className={cn('mt-[3px] size-[18px] shrink-0', s.iconClass)} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <p className="text-base font-semibold text-foreground">{title}</p>
        {children && <div className="text-base leading-relaxed text-foreground/75">{children}</div>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2 self-center">{action}</div>}
    </div>
  )
}
