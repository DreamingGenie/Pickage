import { SparklesIcon } from 'lucide-react'

import { Skeleton } from '@/components/ui/skeleton'

/**
 * 생태계 탭 맨 위 요약 — 고른 패키지들이 **무엇을 하는지(공통 기능)** 와 **쓰임이 어떻게 움직이는지(흐름)**
 * 를 두 문장으로 묶는다.
 *
 * 문장은 `GET /api/packages/summary` 가 LLM 으로 쓴다(실험). 없거나 실패하면 자리만 두고 안내문을 보여준다 —
 * 지어낸 요약을 넣지 않는다. 어느 쪽이 낫다고 판정하지 않는다(IA 1-12).
 */
export type EcosystemSummaryState =
  { kind: 'loading' } | { kind: 'ready'; common: string; ecosystem: string } | { kind: 'none' }

export function EcosystemSummary({
  names,
  summary,
}: {
  names: readonly string[]
  summary: EcosystemSummaryState
}) {
  return (
    <section
      aria-labelledby="eco-summary-title"
      aria-busy={summary.kind === 'loading'}
      className="flex flex-col gap-3 rounded-2xl border bg-card p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="eco-summary-title" className="flex items-center gap-2 text-xl font-bold">
          <SparklesIcon aria-hidden className="size-5" />
          한눈에 보기
        </h2>
        <span className="font-mono text-sm text-muted-foreground">{names.join(' · ')}</span>
      </div>
      {summary.kind === 'loading' ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-4/5" />
        </div>
      ) : summary.kind === 'ready' ? (
        <div className="flex flex-col gap-2 text-lg leading-relaxed text-foreground/85">
          <p>{summary.common}</p>
          <p>{summary.ecosystem}</p>
        </div>
      ) : (
        <p className="text-lg leading-relaxed text-muted-foreground">
          지금은 요약을 준비하지 못했어요. 아래 카드와 그래프로 확인해 주세요.
        </p>
      )}
    </section>
  )
}
