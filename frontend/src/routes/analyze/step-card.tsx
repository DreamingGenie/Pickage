import { CheckIcon, PencilIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type StepState = 'done' | 'active' | 'locked'

/**
 * 단계 카드. 끝난 단계는 한 줄로 접히고, 다음 단계가 그 아래에 이어 붙는다.
 * 본인 인증 절차처럼 위에서 아래로 쌓여 지금까지 무엇이 확정됐는지가 계속 보인다.
 */
export function StepCard({
  index,
  title,
  state,
  summary,
  onEdit,
  className,
  children,
}: {
  index: number
  title: string
  state: StepState
  /** 접힌 상태에서 보여줄 확정값 */
  summary?: ReactNode
  onEdit?: () => void
  className?: string
  children?: ReactNode
}) {
  const done = state === 'done'
  const locked = state === 'locked'

  return (
    <li
      data-state={state}
      className={cn(
        'relative rounded-2xl border transition-[opacity,border-color,box-shadow] duration-300',
        className,
        state === 'active' &&
          'border-foreground/35 bg-background shadow-[0_4px_24px_-14px_rgba(15,23,42,0.35)]',
        done && 'bg-muted/30',
        locked && 'bg-muted/20 opacity-45',
      )}
    >
      <div className={cn('flex items-center gap-3 px-6', done || locked ? 'py-4' : 'pt-6 pb-2')}>
        <span
          className={cn(
            'grid size-6 shrink-0 place-items-center rounded-full font-mono text-[11px] tabular-nums transition-colors',
            done && 'bg-emerald-600 text-white',
            state === 'active' && 'bg-foreground text-background',
            locked && 'bg-muted text-muted-foreground',
          )}
        >
          {done ? <CheckIcon className="size-3.5" strokeWidth={3} aria-hidden /> : index}
        </span>

        <span className={cn('text-sm font-semibold', locked && 'text-muted-foreground')}>
          {title}
        </span>

        {done && summary && (
          <span className="ml-auto flex min-w-0 items-center gap-3">
            <span className="truncate text-[13px]">{summary}</span>
            {onEdit && (
              <button
                type="button"
                onClick={onEdit}
                className="flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
              >
                <PencilIcon className="size-3" aria-hidden />
                수정
              </button>
            )}
          </span>
        )}
      </div>

      {state === 'active' && children && <div className="px-6 pt-2 pb-6">{children}</div>}
    </li>
  )
}

/** 카드 사이를 잇는 세로선. 절차가 이어진다는 걸 형태로 보여준다. */
export function StepConnector({ active }: { active: boolean }) {
  return (
    <li aria-hidden className="flex justify-start pl-[calc(1.5rem+11px)]">
      <span
        className={cn(
          'h-5 w-px transition-colors duration-300',
          active ? 'bg-foreground/35' : 'bg-border',
        )}
      />
    </li>
  )
}
