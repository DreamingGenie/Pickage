import type { CSSProperties } from 'react'

import { cn } from '@/lib/utils'
import type { ComparisonView } from '@/routes/report/features/model'

/**
 * AI 기능 비교 결과 — 공통점 한 덩어리 + 패키지별 차이점 문단 (2026-09-22, 판정표 대신).
 *
 * 차이점은 패키지를 나란히 놓는다(넓은 화면에서 열). 어느 쪽이 낫다고 판정하지 않는다(IA 1-12).
 */
export function ComparisonNarrative({
  view,
  dimmed,
  note,
}: {
  view: ComparisonView
  dimmed: boolean
  /** README 가 짧은 패키지가 있을 때 한 줄 */
  note?: string | null
}) {
  return (
    <div className={cn('flex flex-col gap-5 transition-opacity', dimmed && 'opacity-60')}>
      {view.limited && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
          자료가 부족해 일부만 설명했어요.
        </p>
      )}

      <section
        aria-labelledby="common-title"
        className="flex flex-col gap-2 rounded-2xl border p-6"
      >
        <h4 id="common-title" className="text-lg font-bold">
          공통점
        </h4>
        <p className="text-base leading-relaxed">{view.common}</p>
      </section>

      <section aria-labelledby="differences-title" className="flex flex-col gap-3">
        <h4 id="differences-title" className="text-lg font-bold">
          차이점
        </h4>
        <div
          className="grid items-stretch gap-4 md:grid-cols-[repeat(var(--cols),minmax(0,1fr))]"
          style={{ '--cols': view.differences.length } as CSSProperties}
        >
          {view.differences.map((d) => (
            <article key={d.name} className="flex flex-col gap-2 rounded-2xl border p-5">
              <h5 className="flex flex-wrap items-baseline gap-x-2 text-base font-semibold">
                <span className="font-mono">{d.name}</span>
                <span className="font-mono text-sm font-normal text-muted-foreground">
                  {d.version}
                </span>
              </h5>
              {d.body ? (
                <p className="text-base leading-relaxed">{d.body}</p>
              ) : (
                <p className="text-base text-muted-foreground">
                  이 패키지는 설명을 만들지 못했어요.
                </p>
              )}
            </article>
          ))}
        </div>
      </section>

      {note && <p className="text-base leading-relaxed text-muted-foreground">{note}</p>}
    </div>
  )
}
