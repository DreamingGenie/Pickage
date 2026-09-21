import {
  CheckIcon,
  CircleMinusIcon,
  CircleQuestionMarkIcon,
  TriangleAlertIcon,
  XIcon,
  type LucideIcon,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import { VERDICT_LABEL, type Verdict } from '@/routes/report/features/sample'

/**
 * 구상안 §7.2 verdict 5종.
 *
 * **색만으로 의미를 전하지 않는다**(IA §1-13) — 아이콘과 글자를 함께 쓴다. 미확인은 실패색을
 * 쓰지 않는다. 자료에서 확인되지 않은 것이지 지원하지 않는다는 뜻이 아니다.
 */
const STYLE: Record<Verdict, { className: string; Icon: LucideIcon }> = {
  SUPPORTED: { className: 'bg-emerald-50 text-emerald-700', Icon: CheckIcon },
  CONDITIONALLY_SUPPORTED: { className: 'bg-amber-50 text-amber-700', Icon: TriangleAlertIcon },
  LIMITED_SUPPORT: { className: 'bg-amber-50 text-amber-700', Icon: CircleMinusIcon },
  UNCONFIRMED: { className: 'bg-muted text-muted-foreground', Icon: CircleQuestionMarkIcon },
  UNSUPPORTED: { className: 'bg-red-50 text-red-700', Icon: XIcon },
}

export function VerdictPill({ verdict, className }: { verdict: Verdict; className?: string }) {
  const { className: tone, Icon } = STYLE[verdict]
  return (
    <span
      className={cn(
        'inline-flex w-fit items-center gap-1 rounded px-1.5 py-0.5 text-base font-medium',
        tone,
        className,
      )}
    >
      <Icon className="size-3" strokeWidth={2.5} aria-hidden />
      {VERDICT_LABEL[verdict]}
    </span>
  )
}
