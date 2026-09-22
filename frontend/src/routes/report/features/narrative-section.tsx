import { cn } from '@/lib/utils'
import type { ComparisonView } from '@/routes/report/features/model'

/**
 * 기능 비교 해설 (IA §9.5).
 *
 * 표의 판정을 그대로 반복하지 않고, 기능을 구성하는 방식과 확인해야 할 조건을 근거 중심으로
 * 설명한다. **추천·순위·승자를 매기지 않는다**(IA §1-12) — 실제로 순위·승자를 매기는 문구를
 * 만들지 않는 것으로 지킨다.
 *
 * 표는 있는데 해설만 못 만든 경우(`narrativeError`)는 표의 판정과 근거가 그대로 유효하므로
 * 이 섹션만 실패로 알린다. 해설이 없다는 이유로 표를 물리지 않는다.
 *
 * 하단에 "추천하지 않는다" 는 상시 고지를 뒀었으나, 글이 줄어 화면이 압축된 지금은 매 카드마다
 * 반복해 읽을 만큼의 정보가 아니라 QA 피드백으로 뺐다(S15P21A506-465 후속) — 실제로 추천·순위
 * 문구를 만들지 않는 것이 규칙을 지키는 것이지, 문구로 고지하는 것이 규칙 자체는 아니다.
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
          표에서 드러나지 않는 차이와, 고를 때 확인해 볼 점을 정리했습니다.
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
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
