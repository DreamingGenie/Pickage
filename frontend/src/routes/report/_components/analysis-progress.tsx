import { CheckIcon, Loader2Icon } from 'lucide-react'

import { Skeleton } from '@/components/ui/skeleton'
import { RUN_STEPS, type AnalysisRun } from '@/routes/report/_components/use-analysis-run'
import { cn } from '@/lib/utils'

/**
 * 최초 분석 대기 화면 (IA 9.4).
 *
 * 스피너 하나로 30초를 버티게 하지 않는다. 어디까지 끝났는지 단계로 보여주고,
 * 결과가 들어올 자리는 skeleton 으로 미리 잡아 둔다.
 *
 * 아직 끝나지 않은 단계에는 체크를 올리지 않는다.
 */
export function AnalysisProgress({
  run,
  packages,
  /** 이전 결과를 그대로 두고 진행만 알리는 재분석 모드 (IA 9.4) */
  compactCard = false,
  className,
}: {
  run: AnalysisRun
  packages: readonly string[]
  compactCard?: boolean
  className?: string
}) {
  const total = RUN_STEPS.length
  const pct = Math.round((run.doneCount / total) * 100)

  return (
    <div className={cn('flex flex-col gap-5', className)}>
      <section
        className={cn(
          'flex flex-col gap-4 rounded-2xl border p-6',
          compactCard && 'border-foreground/30 bg-muted/30',
        )}
      >
        <header className="flex flex-wrap items-baseline justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <Loader2Icon className="size-4 animate-spin text-muted-foreground" aria-hidden />
            <h3 className="text-sm font-semibold">
              {compactCard ? '선택한 버전으로 재분석 중' : '기능 비교 분석 중'}
            </h3>
          </div>
          <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
            {run.doneCount} / {total} 단계 · {run.elapsedSec}초
          </span>
        </header>

        <div className="flex flex-wrap gap-1.5">
          {packages.map((p) => (
            <span key={p} className="rounded border px-1.5 py-0.5 font-mono text-[11px]">
              {p}
            </span>
          ))}
        </div>

        {/* 진행 막대 — 값은 완료된 단계 수에서만 나온다 */}
        <div
          className="h-1.5 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="기능 분석 진행률"
        >
          <div
            className="h-full rounded-full bg-foreground transition-[width] duration-500 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>

        <ol className="flex flex-col gap-2.5">
          {RUN_STEPS.map((s, i) => {
            const done = i < run.doneCount
            const current = i === run.doneCount
            return (
              <li
                key={s.key}
                className={cn(
                  'flex items-center gap-2.5 text-[13px] transition-opacity duration-300',
                  !done && !current && 'text-muted-foreground opacity-45',
                  current && 'font-medium',
                )}
              >
                <span
                  className={cn(
                    'grid size-4 shrink-0 place-items-center rounded-full',
                    done && 'bg-emerald-600 text-white',
                    current && 'border border-foreground/40',
                    !done && !current && 'border border-border',
                  )}
                >
                  {done && <CheckIcon className="size-2.5" strokeWidth={3.5} aria-hidden />}
                  {current && (
                    <span className="size-1.5 animate-pulse rounded-full bg-foreground" />
                  )}
                </span>
                {s.label}
              </li>
            )
          })}
        </ol>

        <p className="border-t pt-3 text-[11.5px] leading-relaxed text-muted-foreground">
          {compactCard
            ? '이전 결과는 그대로 두었습니다. 새 분석이 성공해야만 표가 교체됩니다.'
            : '정확한 버전의 배포본을 내려받아 정적으로 읽는 중입니다. 패키지를 설치하거나 실행하지 않습니다. 생태계 변화 탭은 지금 바로 볼 수 있습니다.'}
        </p>
      </section>

      {!compactCard && <ResultSkeleton />}
    </div>
  )
}

/** 결과가 들어올 자리를 미리 잡아 둔다. 완료되면 같은 자리에 표가 들어온다. */
function ResultSkeleton() {
  return (
    <section aria-hidden className="flex flex-col gap-4 rounded-2xl border p-6">
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-4 w-20" />
      </div>
      <div className="flex flex-col gap-2.5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="grid grid-cols-[1.4fr_1fr_1fr_1fr] gap-3">
            <Skeleton className="h-7" />
            <Skeleton className="h-7" />
            <Skeleton className="h-7" />
            <Skeleton className="h-7" />
          </div>
        ))}
      </div>
    </section>
  )
}
