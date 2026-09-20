import { cn } from '@/lib/utils'
import type { ComparisonView } from '@/routes/report/features/model'

/**
 * 기능 비교 해설 (IA §9.5).
 *
 * 표의 판정을 그대로 반복하지 않고, 기능을 구성하는 방식과 확인해야 할 조건을 근거 중심으로
 * 설명한다. **추천·순위·승자를 매기지 않는다** — 하단 고지가 그것을 밝힌다.
 *
 * 표는 있는데 해설만 못 만든 경우(`narrativeError`)는 표의 판정과 근거가 그대로 유효하므로
 * 이 섹션만 실패로 알린다. 해설이 없다는 이유로 표를 물리지 않는다.
 */
export function NarrativeSection({ view, dimmed }: { view: ComparisonView; dimmed: boolean }) {
  if (view.narrative.length === 0 && !view.narrativeError) return null

  return (
    <section
      aria-labelledby="narrative-title"
      className={cn(
        'flex flex-col gap-5 rounded-2xl border p-6 transition-opacity',
        dimmed && 'opacity-60',
      )}
    >
      <header className="flex flex-col gap-1.5">
        <h3 id="narrative-title" className="text-sm font-semibold">
          기능 비교 해설
        </h3>
        <p className="text-base text-muted-foreground">
          표의 판정을 그대로 반복하지 않고, 기능을 구성하는 방식과 확인해야 할 조건을 근거 중심으로
          설명합니다.
        </p>
      </header>

      {view.narrativeError ? (
        <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
          해설을 만들지 못했습니다. 위 표의 판정과 근거는 그대로 확인할 수 있습니다.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {view.narrative.map((section) => (
            <div key={section.heading} className="flex flex-col gap-1.5 rounded-xl bg-muted/40 p-4">
              <h4 className="text-base font-semibold">{section.heading}</h4>
              <p className="text-base leading-relaxed">{section.body}</p>
              {section.evidenceIds.length > 0 && (
                <p className="font-mono text-base text-muted-foreground">
                  근거 {section.evidenceIds.join(' · ')}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      <p className="rounded-lg bg-muted/40 px-4 py-3 text-base leading-relaxed text-muted-foreground">
        추천 · 순위 · 승자 표시는 제공하지 않습니다. 각 문장은 근거의 evidence ID와 연결되며, 근거가
        부족하면 &lsquo;미확인&rsquo;으로 남습니다.
      </p>
    </section>
  )
}
