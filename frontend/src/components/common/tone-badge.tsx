import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * 뜻을 가진 작은 딱지. "1년 사이 늘었어요" · "바뀜" · "지원 종료" 같은 한마디를 붙인다.
 *
 * 색은 `index.css` 의 상태 톤 토큰에서만 온다. **글자가 늘 함께 있어야 한다** — 색만으로
 * 늘었다·줄었다를 알리지 않는다(IA 1-13). 그래서 children 은 필수다.
 *
 *   up       늘었어요·새로 생겼어요 (좋다·나쁘다의 판정이 아니다)
 *   down     줄었어요·주의해서 볼 것
 *   positive 확인됐어요·지원
 *   neutral  변화 없음·자료 없음 — 실패색을 쓰지 않는다
 *   danger   오류·지원 종료처럼 사용자가 꼭 알아야 하는 것
 *   brand    선택·강조
 */
export type Tone = 'up' | 'down' | 'positive' | 'neutral' | 'danger' | 'brand'

const TONE_CLASS: Record<Tone, string> = {
  up: 'bg-tone-up text-tone-up-foreground',
  down: 'bg-tone-down text-tone-down-foreground',
  positive: 'bg-tone-positive text-tone-positive-foreground',
  neutral: 'bg-tone-neutral text-tone-neutral-foreground',
  danger: 'bg-tone-danger text-tone-danger-foreground',
  brand: 'bg-brand-soft text-primary',
}

export function ToneBadge({
  tone,
  icon,
  className,
  children,
}: {
  tone: Tone
  icon?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <span
      className={cn(
        'inline-flex w-fit items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-medium whitespace-nowrap [&_svg]:size-4 [&_svg]:shrink-0',
        TONE_CLASS[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  )
}
