import { CheckIcon, XIcon } from 'lucide-react'

import { Notice } from '@/components/common/notice'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/**
 * 선택 패널 — 무엇을 골랐는지 늘 보이게 오른쪽에 붙인다.
 *
 * 상태는 갖지 않는다. 고른 목록·한도 초과·생성 중 여부는 `AnalyzePage` 가 들고, 여기는 그리기만 한다.
 * 첫 항목은 기준 패키지라 뺄 수 없다(IA 6.3).
 */
export function SelectionPanel({
  selected,
  max,
  limitHit,
  creating,
  lastAdded,
  onRemove,
  onCreate,
}: {
  /** 기준 패키지가 맨 앞이다 */
  selected: readonly string[]
  /** 기준 포함 최대 비교 수 */
  max: number
  /** 한도를 넘겨 고르려 했는지 */
  limitHit: boolean
  creating: boolean
  /** 방금 추가한 패키지. 아직 골라져 있을 때만 넘긴다 — "추가했어요 · 되돌리기" 알림에 쓴다 */
  lastAdded: string | null
  onRemove: (name: string) => void
  onCreate: () => void
}) {
  const full = selected.length >= max
  return (
    <aside className="flex animate-in flex-col gap-4 duration-300 fade-in-0 slide-in-from-right-4 lg:sticky lg:top-6">
      <div className="flex flex-col gap-4 rounded-2xl border bg-card p-5">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">비교할 패키지</h2>
          <span className="font-mono text-base text-muted-foreground tabular-nums">
            {selected.length} / {max}
          </span>
        </div>
        <ul className="flex flex-col gap-2">
          {selected.map((n, i) => (
            <li
              key={n}
              className={cn(
                'flex min-w-0 items-center gap-2 rounded-lg border px-3 py-2',
                i === 0 ? 'bg-muted/50' : 'bg-card',
              )}
            >
              {i === 0 && (
                <span className="shrink-0 rounded-full bg-brand-soft px-2 py-0.5 text-sm font-medium text-primary">
                  기준
                </span>
              )}
              <span title={n} className="min-w-0 flex-1 truncate font-mono text-base">
                {n}
              </span>
              {i > 0 && (
                <button
                  type="button"
                  onClick={() => onRemove(n)}
                  aria-label={`${n} 비교에서 빼기`}
                  className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <XIcon className="size-4" aria-hidden />
                </button>
              )}
            </li>
          ))}
          {!full && (
            <li className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
              {max - selected.length}개 더 고를 수 있어요
            </li>
          )}
        </ul>

        {limitHit && (
          <Notice tone="warn" title={`한 번에 ${max}개까지 비교할 수 있어요`}>
            고른 것 중 하나를 빼면 새로 넣을 수 있어요.
          </Notice>
        )}

        <Button size="lg" className="w-full" disabled={creating} onClick={onCreate}>
          {selected.length === 1
            ? '기준 패키지만 보고서 보기'
            : `${selected.length}개로 보고서 보기`}
        </Button>
      </div>

      {/* 방금 넣은 것 — 추가가 눈에 띄지 않는다는 의견으로 넣었다. 되돌리기로 바로 뺄 수 있다. */}
      {lastAdded && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-xl bg-tone-positive px-4 py-3 text-base text-tone-positive-foreground"
        >
          <CheckIcon className="size-4 shrink-0" aria-hidden />
          <span className="min-w-0 flex-1 truncate">
            <span className="font-mono font-semibold">{lastAdded}</span> 를 추가했어요
          </span>
          <button
            type="button"
            onClick={() => onRemove(lastAdded)}
            className="shrink-0 font-semibold underline underline-offset-2"
          >
            되돌리기
          </button>
        </div>
      )}
    </aside>
  )
}
