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
}: {
  steps?: StepperStep[]
  currentId: string
  className?: string
}) {
  const currentIndex = steps.findIndex((s) => s.id === currentId)

  return (
    <ol className={cn('flex items-center gap-3', className)}>
      {steps.map((step, i) => {
        const state = i < currentIndex ? 'done' : i === currentIndex ? 'current' : 'todo'
        return (
          <li key={step.id} className="flex items-center gap-3">
            <span className="flex items-center gap-2">
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
                  state === 'todo' ? 'text-muted-foreground' : 'text-foreground',
                )}
              >
                {step.label}
              </span>
            </span>
            {i < steps.length - 1 && <span className="h-px w-8 bg-border" aria-hidden />}
          </li>
        )
      })}
    </ol>
  )
}
