import { cn } from '@/lib/utils'

export interface StepperStep {
  id: string
  label: string
}

export const ANALYZE_STEPS: StepperStep[] = [
  { id: 'input', label: '패키지 입력' },
  { id: 'candidates', label: '후보 선택' },
  { id: 'report', label: '리포트' },
]

export function Stepper({
  steps = ANALYZE_STEPS,
  currentId,
  className,
  onStepClick,
}: {
  steps?: StepperStep[]
  currentId: string
  className?: string
  /** 있으면 지나온 단계를 눌러 그 단계로 돌아갈 수 있다. 지금·앞 단계는 누를 수 없다. */
  onStepClick?: (id: string) => void
}) {
  const currentIndex = steps.findIndex((s) => s.id === currentId)

  return (
    <ol className={cn('flex items-center gap-3', className)}>
      {steps.map((step, i) => {
        const state: 'done' | 'current' | 'todo' =
          i < currentIndex ? 'done' : i === currentIndex ? 'current' : 'todo'
        const content = (
          <>
            <span
              className={cn(
                'flex size-6 items-center justify-center rounded-full border text-xs font-medium',
                state === 'current' && 'border-primary bg-primary text-primary-foreground',
                state === 'done' && 'bg-muted text-foreground',
                state === 'todo' && 'text-muted-foreground',
              )}
            >
              {i + 1}
            </span>
            <span
              className={cn(
                'text-sm',
                // 진행 중·끝난 단계는 굵게, 아직 오지 않은 단계는 옅게
                state === 'todo' ? 'text-muted-foreground' : 'font-semibold text-foreground',
              )}
            >
              {step.label}
            </span>
          </>
        )
        return (
          <li key={step.id} className="flex items-center gap-3">
            {state === 'done' && onStepClick ? (
              <button
                type="button"
                onClick={() => onStepClick(step.id)}
                aria-label={`${step.label} 단계로 돌아가기`}
                className="flex items-center gap-2 rounded-md underline-offset-4 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/40"
              >
                {content}
              </button>
            ) : (
              <span
                className="flex items-center gap-2"
                aria-current={state === 'current' ? 'step' : undefined}
              >
                {content}
              </span>
            )}
            {i < steps.length - 1 && <span className="h-px w-8 bg-border" aria-hidden />}
          </li>
        )
      })}
    </ol>
  )
}
